# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class TaskManagement(models.Model):
    _name = 'task.management'
    _description = 'Task Management'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _rec_name = 'name'
    _order = 'priority desc, sequence, date_deadline asc, id desc'
    _check_company_auto = True

    # Basic Fields
    name = fields.Char(
        string='Task Title',
        required=True,
        tracking=True,
        index=True,
        help='Enter the task title'
    )
    
    description = fields.Html(
        string='Description',
        sanitize=True,
        help='Detailed description of the task with rich text formatting'
    )
    
    active = fields.Boolean(default=True, string='Active')
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color Index', default=0)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env. company)
    
    # Task Type - to distinguish between individual and team tasks
    task_type = fields.Selection([
        ('individual', 'Individual Task'),
        ('team', 'Team Task')
    ], string='Task Type', default='individual', required=True, tracking=True)
    
    # User Assignment Fields
    user_id = fields.Many2one(
        'res.users',
        string='Delegated to',
        default=lambda self: self.env.user if self.env.context.get('default_task_type') != 'team' else False,
        tracking=True,
        domain="[('share', '=', False), ('active', '=', True)]",
        index=True
    )
    
    # Team field - for team tasks
    team_id = fields.Many2one(
        'task.team',
        string='Team',
        ondelete='cascade',
        tracking=True
    )
    
    # Additional collaborators (using team_ids for compatibility)
    team_ids = fields.Many2many(
        'res.users',
        'task_team_users_rel',
        'task_id',
        'user_id',
        string='Additional Collaborators',
        domain="[('share', '=', False), ('active', '=', True)]",
        help='Additional users who can access this task'
    )
    
    # Stage and State Management
    stage_id = fields.Many2one(
        'task.stage',
        string='Stage',
        tracking=True,
        index=True,
        copy=False,
        group_expand='_read_group_stage_ids',
        default=lambda self: self._get_default_stage_id()
    )
    
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked')
    ], string='Kanban State', default='normal', tracking=True)
    
    # Priority and Tags
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority', default='1', tracking=True, index=True)
    
    tag_ids = fields.Many2many(
        'task.tag',
        'task_tags_rel',
        'task_id',
        'tag_id',
        string='Tags',
        help='Classify and filter tasks using tags'
    )
    
    # Date Fields
    date_deadline = fields.Date(
        string='Deadline',
        tracking=True,
        index=True,
        help='Deadline for task completion'
    )

    date_start = fields.Date(
        string='Start Date',
        default=fields.Date.today,
        tracking=True,
        help='Task start date'
    )

    date_end = fields.Date(
        string='End Date',
        tracking=True,
        help='Task completion date'
    )

    date_assign = fields.Date(
        string='Assignment Date',
        tracking=True,
        help='Date when task was last assigned'
    )
    
    # ============================================
    # HIGH-LEVEL TIME TRACKING (MANUAL FIELDS)
    # ============================================
    planned_hours = fields.Float(
        string='Planned Time',
        tracking=True,
        help='High-level planned time (manual entry)'
    )
    
    effective_hours = fields.Float(
        string='Actual Time',
        tracking=True,
        help='Actual time consumed on this task (manual entry)'
    )
    
    remaining_hours = fields.Float(
        string='Time Remaining',
        compute='_compute_remaining_hours',
        store=True,
        help='Remaining time calculated from estimates'
    )
    
    # ============================================
    # TIME LOG TRACKING (FROM DETAILED ENTRIES)
    # ============================================
    timesheet_ids = fields.One2many(
        'task.timesheet.line',
        'task_id',
        string='Time Logs'
    )

    allow_timesheets = fields.Boolean(
        string='Allow Time Logs',
        default=True,
        help='Enable time log entries for this task'
    )
    
    # COMPUTED: Total Planned Time from all time log entries
    total_planned_hours_from_logs = fields.Float(
        string='Total Planned Time (Logs)',
        compute='_compute_timesheet_totals',
        store=True,
        help='Sum of all Planned Time from time log entries'
    )
    
    # COMPUTED: Total Logged Hours from all time log entries
    total_logged_hours = fields.Float(
        string='Total Actual Time Logged',
        compute='_compute_timesheet_totals',
        store=True,
        help='Sum of all Actual Time Logged from time log entries'
    )
    
    # COMPUTED: Total Remaining from all time log entries
    total_remaining_hours_from_logs = fields.Float(
        string='Total Remaining (Logs)',
        compute='_compute_timesheet_totals',
        store=True,
        help='Sum of all Remaining hours from time log entries'
    )

    # ============================================
    # PROGRESS & PERFORMANCE - HIGH LEVEL
    # ============================================
    task_progress = fields.Float(
        string='Task Progress %',
        compute='_compute_task_progress',
        store=True,
        help='Progress based on Actual Time vs Planned Time'
    )

    task_performance = fields.Selection([
        ('over_estimated', 'Over Estimated'),
        ('on_track', 'On Track'),
        ('under_estimated', 'Under Estimated'),
        ('not_started', 'Not Started')
    ], string='Task Performance', compute='_compute_task_performance', store=True,
       help='Performance based on Planned Time vs Actual Time')

    # ============================================
    # PROGRESS & PERFORMANCE - TIME LOGS (DYNAMIC FROM ENTRIES)
    # ============================================
    timesheet_progress = fields.Float(
        string='Time Log Progress %',
        compute='_compute_timesheet_progress',
        store=True,
        help='Progress calculated from sum of time log entries'
    )

    timesheet_performance = fields.Selection([
        ('over_estimated', 'Over Estimated'),
        ('on_track', 'On Track'),
        ('under_estimated', 'Under Estimated'),
        ('not_started', 'Not Started')
    ], string='Time Log Performance', compute='_compute_timesheet_performance', store=True,
       help='Performance calculated from sum of time log entries')

    # ============================================
    # ALLOCATED TIME CHANGE TRACKING (HIGH LEVEL ONLY)
    # ============================================
    planned_hours_change_count = fields.Integer(
        string='Planned Time Changes',
        default=0,
        readonly=True,
        help='Number of times Planned Time has been modified'
    )

    planned_hours_last_changed = fields.Datetime(
        string='Last Planned Time Change',
        readonly=True,
        help='When Planned Time was last modified'
    )

    planned_hours_changed_by = fields.Many2one(
        'res.users',
        string='Last Changed By',
        readonly=True,
        help='User who last modified Planned Time'
    )

    planned_hours_history = fields.Text(
        string='Planned Time History',
        readonly=True,
        help='History of all Planned Time changes'
    )
    
    # Subtasks
    subtask_ids = fields.One2many(
        'task.subtask',
        'parent_task_id',
        string='Subtasks'
    )
    
    subtask_count = fields.Integer(
        string='Subtask Count',
        compute='_compute_subtask_count',
        store=True
    )
    
    subtask_completed_count = fields.Integer(
        string='Completed Subtasks',
        compute='_compute_subtask_count',
        store=True
    )
    
    # Parent Task (for hierarchical tasks)
    parent_id = fields.Many2one(
        'task.management',
        string='Parent Task',
        index=True
    )
    
    child_ids = fields.One2many(
        'task.management',
        'parent_id',
        string='Sub-tasks'
    )
    
    # Recurrence Fields
    recurring_task = fields.Boolean(string='Recurring Task', default=False)
    recurrence_id = fields.Many2one('task.recurrence', string='Recurrence')
    recurrence_update = fields.Selection([
        ('this', 'This task'),
        ('subsequent', 'This and following tasks'),
        ('all', 'All tasks')
    ], default='this', store=False)
    
    # Additional Information
    checklist_items = fields.Html(
        string='Checklist',
        sanitize=False,
        sanitize_tags=False,
        sanitize_attributes=False
    )

    notes = fields.Html(
        string='Internal Notes',
        sanitize=False,
        sanitize_tags=False,
        sanitize_attributes=False
    )
    
    displayed_image_id = fields.Many2one(
        'ir.attachment',
        domain="[('res_model', '=', 'task.management'), ('res_id', '=', id), ('mimetype', 'ilike', 'image')]",
        string='Cover Image'
    )
    
    # Customer/Partner
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    
    partner_email = fields.Char(
        string='Customer Email',
        related='partner_id.email',
        readonly=False
    )
    
    partner_phone = fields.Char(
        string='Customer Phone',
        related='partner_id.phone',
        readonly=False
    )
    
    # Template field
    template_id = fields.Many2one('task.template', string='Created from Template')
    
    # Computed Fields
    is_closed = fields.Boolean(
        string='Is Closed',
        compute='_compute_is_closed',
        store=True
    )
    
    days_to_deadline = fields.Integer(
        string='Days to Deadline',
        compute='_compute_days_to_deadline',
        store=True
    )
    
    is_user_team_task = fields.Boolean(
        string='Is User Team Task',
        compute='_compute_is_user_team_task'
    )
    
    task_category = fields.Selection([
        ('created', 'Created by Me'),
        ('delegated', 'Delegated by Me'),
        ('other', 'Other Tasks')
    ], string='Task Category', compute='_compute_task_category', store=True, default='other')
    
    # ========== COMPUTE METHODS ==========
    
    def _get_default_stage_id(self):
        """Get default stage for new tasks"""
        return self.env['task.stage'].search([('name', '=', 'To-Do')], limit=1)
    
    @api.depends('timesheet_ids.planned_hours', 'timesheet_ids.unit_amount', 'timesheet_ids.remaining_hours')
    def _compute_timesheet_totals(self):
        """Calculate totals from time log entries (DYNAMIC)"""
        for task in self:
            task.total_planned_hours_from_logs = sum(task.timesheet_ids.mapped('planned_hours'))
            task.total_logged_hours = sum(task.timesheet_ids.mapped('unit_amount'))
            task.total_remaining_hours_from_logs = sum(task.timesheet_ids.mapped('remaining_hours'))
    
    @api.depends('planned_hours', 'effective_hours')
    def _compute_remaining_hours(self):
        """Calculate remaining hours from manual estimates (independent from time logs)"""
        for task in self:
            task.remaining_hours = (task.planned_hours or 0.0) - (task.effective_hours or 0.0)
    
    @api.depends('subtask_ids', 'subtask_ids.is_done')
    def _compute_subtask_count(self):
        for task in self:
            task.subtask_count = len(task.subtask_ids)
            task.subtask_completed_count = len(task.subtask_ids.filtered('is_done'))
    
    @api.depends('stage_id', 'stage_id.is_closed')
    def _compute_is_closed(self):
        for task in self:
            task.is_closed = task.stage_id.is_closed if task.stage_id else False
    
    @api.depends('date_deadline')
    def _compute_days_to_deadline(self):
        today = fields.Date.today()
        for task in self:
            if task.date_deadline:
                deadline_date = task.date_deadline.date() if isinstance(task.date_deadline, datetime) else task.date_deadline
                task.days_to_deadline = (deadline_date - today).days
            else:
                task.days_to_deadline = 0
    
    @api.depends('team_id', 'team_id.manager_id', 'team_id.member_ids')
    def _compute_is_user_team_task(self):
        current_user = self.env.user
        for task in self:
            if task.team_id:
                task.is_user_team_task = (
                    task.team_id.manager_id == current_user or
                    current_user in task.team_id.member_ids
                )
            else:
                task.is_user_team_task = False
    
    @api.depends('create_uid', 'user_id')
    def _compute_task_category(self):
        current_uid = self.env.uid
        for task in self:
            if task.create_uid.id == current_uid:
                if task.user_id and task.user_id.id != current_uid:
                    task.task_category = 'delegated'
                else:
                    task.task_category = 'created'
            else:
                task.task_category = 'other'

    # ========== PROGRESS & PERFORMANCE COMPUTE METHODS ==========

    @api.depends('planned_hours', 'effective_hours')
    def _compute_task_progress(self):
        """Calculate task progress percentage"""
        for task in self:
            if task.planned_hours > 0:
                task.task_progress = round(100.0 * task.effective_hours / task.planned_hours)
            else:
                task.task_progress = 0.0

    @api.depends('planned_hours', 'effective_hours')
    def _compute_task_performance(self):
        """
        LOGIC:
        - Over Estimated: Planned > Actual (finished faster)
        - Under Estimated: Planned < Actual (took longer)
        - On Track: 80-100% usage
        """
        for task in self:
            if not task.planned_hours or task.planned_hours == 0:
                task.task_performance = 'not_started'
                continue
            
            planned = task.planned_hours
            actual = task.effective_hours
            
            if planned > actual:
                # Planned MORE than actual = Over Estimated
                usage_percent = (actual / planned) * 100
                if usage_percent >= 80:
                    task.task_performance = 'on_track'  # 80-100% usage
                else:
                    task.task_performance = 'over_estimated'  # < 80% usage
            elif planned < actual:
                # Planned LESS than actual = Under Estimated
                task.task_performance = 'under_estimated'
            else:
                # Planned == Actual = Perfect
                task.task_performance = 'on_track'

    @api.depends('timesheet_ids.planned_hours', 'timesheet_ids.unit_amount')
    def _compute_timesheet_progress(self):
        """Calculate time log progress from SUM of entries"""
        for task in self:
            total_planned = sum(task.timesheet_ids.mapped('planned_hours'))
            total_logged = sum(task.timesheet_ids.mapped('unit_amount'))
            
            if total_planned > 0:
                task.timesheet_progress = round(100.0 * total_logged / total_planned)
            else:
                task.timesheet_progress = 0.0

    @api.depends('timesheet_ids.planned_hours', 'timesheet_ids.unit_amount')
    def _compute_timesheet_performance(self):
        """
        Calculate performance from SUM of time log entries
        LOGIC:
        - Over Estimated: Total Planned > Total Logged (finished faster)
        - Under Estimated: Total Planned < Total Logged (took longer)
        - On Track: 80-100% usage
        """
        for task in self:
            total_planned = sum(task.timesheet_ids.mapped('planned_hours'))
            total_logged = sum(task.timesheet_ids.mapped('unit_amount'))
            
            if not total_planned or total_planned == 0:
                task.timesheet_performance = 'not_started'
                continue
            
            if total_planned > total_logged:
                # Planned MORE than logged = Over Estimated
                usage_percent = (total_logged / total_planned) * 100
                if usage_percent >= 80:
                    task.timesheet_performance = 'on_track'  # 80-100% usage
                else:
                    task.timesheet_performance = 'over_estimated'  # < 80% usage
            elif total_planned < total_logged:
                # Planned LESS than logged = Under Estimated
                task.timesheet_performance = 'under_estimated'
            else:
                # Planned == Logged = Perfect
                task.timesheet_performance = 'on_track'
    
    # ========== ONCHANGE METHODS ==========

    @api.constrains('date_start', 'date_deadline')
    def _check_date_range(self):
        """Ensure due date is not before start date"""
        for task in self:
            if task.date_start and task.date_deadline:
                if task.date_deadline < task.date_start:
                    raise ValidationError(_('Due Date/Delivery Date cannot be set before Start Date/Kickoff Date'))

    @api.onchange('date_start', 'date_deadline')
    def _onchange_date_range(self):
        """Show warning when due date is before start date"""
        if self.date_start and self.date_deadline:
            if self.date_deadline < self.date_start:
                return {
                    'warning': {
                        'title': _('Invalid Date Range'),
                        'message': _('Due Date/Delivery Date cannot be before Start Date/Kickoff Date')
                    }
                }
    
    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            self.date_assign = fields.Datetime.now()

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        """Handle stage changes"""
        if self.stage_id:
            # Auto-set kanban state based on stage
            if self.stage_id.name == 'To-Do':
                self.kanban_state = 'normal'
            elif self.stage_id.name == 'In Progress':
                self.kanban_state = 'normal'
            elif self.stage_id.name == 'Review':
                self.kanban_state = 'normal'
            elif self.stage_id.name == 'Done':
                self.date_end = fields.Datetime.now()
                self.kanban_state = 'done'
            elif self.stage_id.name == 'Cancelled':
                self.kanban_state = 'blocked'
            
            # Set closed status
            if self.stage_id.stage_type in ['done', 'cancelled']:
                self.is_closed = True
            else:
                self.is_closed = False

    @api.onchange('task_type')
    def _onchange_task_type(self):
        if self.task_type == 'individual':
            self.team_id = False
            if not self.user_id:
                self.user_id = self.env.user
        elif self.task_type == 'team':
            self.user_id = False

    @api.onchange('team_id')
    def _onchange_team_id(self):
        if self.team_id and self.task_type != 'team':
            self.task_type = 'team'
    
    @api.model
    def default_get(self, fields_list):
        defaults = super(TaskManagement, self).default_get(fields_list)
        # Set task type based on context
        if self.env.context.get('default_task_type'):
            defaults['task_type'] = self.env.context.get('default_task_type')
        # For individual tasks, set current user
        if defaults.get('task_type') == 'individual':
            defaults['user_id'] = self.env.user.id
        return defaults
    
    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Return all stages for kanban view grouping"""
        return self.env['task.stage'].search([])
    

    # ========== ACTION METHODS ==========
    
    def action_assign_to_me(self):
        self.write({'user_id': self.env.user.id})
    
    def action_open_parent_task(self):
        self.ensure_one()
        if not self.parent_id:
            return {}
        
        return {
            'name': _('Parent Task'),
            'type': 'ir.actions.act_window',
            'res_model': 'task.management',
            'view_mode': 'form',
            'res_id': self.parent_id.id,
        }
    
    def action_view_subtasks(self):
        self.ensure_one()
        return {
            'name': _('Subtasks'),
            'type': 'ir.actions.act_window',
            'res_model': 'task.subtask',
            'view_mode': 'list,form',
            'domain': [('parent_task_id', '=', self.id)],
            'context': {
                'default_parent_task_id': self.id,
            }
        }
    
    def action_view_timesheets(self):
        self.ensure_one()
        return {
            'name': _('Time Logs'),
            'type': 'ir.actions.act_window',
            'res_model': 'task.timesheet.line',
            'view_mode': 'list,form',
            'domain': [('task_id', '=', self.id)],
            'context': {
                'default_task_id': self.id,
                'default_user_id': self.env.user.id,
            }
        }
    
    def action_open_my_tasks(self):
        """Open My Tasks view"""
        return {
            'name': 'My Tasks',
            'type': 'ir.actions.act_window',
            'res_model': 'task.management',
            'view_mode': 'list,kanban,form,calendar',
            'domain': [('task_type', '=', 'individual'), ('user_id', '=', self.env.uid)],
            'context': {
                'default_task_type': 'individual',
                'default_user_id': self.env.uid,
                'search_default_open_tasks': 1
            },
            'target': 'current',
        }

    def action_open_team_tasks(self):
        """Open Team Tasks view"""
        return {
            'name': 'Team Tasks',
            'type': 'ir.actions.act_window',
            'res_model': 'task.management',
            'view_mode': 'list,kanban,form,calendar',
            'domain': [('task_type', '=', 'team')],
            'context': {
                'default_task_type': 'team',
                'search_default_open_tasks': 1,
            },
            'target': 'current',
        }
    
    # ========== CRUD METHODS ==========
    
    @api.model
    def create(self, vals):
        # Set default values based on task type
        if vals.get('task_type') == 'individual':
            if not vals.get('user_id'):
                vals['user_id'] = self.env.user.id
        
        # Set assignment date if user is assigned
        if vals.get('user_id'):
            vals['date_assign'] = fields.Datetime.now()
        
        # Set default stage
        if not vals.get('stage_id'):
            default_stage = self.env['task.stage'].search([('name', '=', 'To-Do')], limit=1)
            if default_stage:
                vals['stage_id'] = default_stage.id
        
        task = super(TaskManagement, self).create(vals)
        
        # Auto-subscribe assigned user or team members
        if task.task_type == 'individual' and task.user_id:
            task.message_subscribe(partner_ids=[task.user_id.partner_id.id])
        elif task.task_type == 'team' and task.team_id:
            partners_to_subscribe = []
            if task.team_id.manager_id:
                partners_to_subscribe.append(task.team_id.manager_id.partner_id.id)
            if task.team_id.member_ids:
                partners_to_subscribe.extend(task.team_id.member_ids.mapped('partner_id').ids)
            if partners_to_subscribe:
                task.message_subscribe(partner_ids=partners_to_subscribe)
        
        return task
    
    def write(self, vals):
        from markupsafe import Markup
        
        # Track user assignment
        if 'user_id' in vals:
            vals['date_assign'] = fields.Datetime.now()
        
        # Track Planned Time changes (HIGH LEVEL ONLY)
        if 'planned_hours' in vals:
            for task in self:
                old_value = task.planned_hours
                new_value = vals['planned_hours']
                
                if old_value != new_value:
                    vals['planned_hours_change_count'] = task.planned_hours_change_count + 1
                    vals['planned_hours_last_changed'] = fields.Datetime.now()
                    vals['planned_hours_changed_by'] = self.env.user.id
                    
                    # Build history
                    history_entry = f"{fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {self.env.user.name}: Changed from {old_value:.2f}h to {new_value:.2f}h\n"
                    vals['planned_hours_history'] = (task.planned_hours_history or '') + history_entry
                    
                    # Post message in chatter
                    message_body = Markup("""
                        <div style="padding: 12px; background-color: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px; margin: 10px 0;">
                            <p style="margin: 0; font-weight: bold; color: #856404; font-size: 14px;">
                                ⚠️ Planned Time Changed
                            </p>
                            <p style="margin: 8px 0 0 0; color: #333;">
                                Changed from <strong style="color: #d9534f;">{:.2f} hours</strong> to <strong style="color: #5cb85c;">{:.2f} hours</strong>
                            </p>
                            <p style="margin: 6px 0 0 0; font-size: 12px; color: #666;">
                                Change #{} • Changed by: {}
                            </p>
                        </div>
                    """.format(old_value, new_value, vals['planned_hours_change_count'], self.env.user.name))
                    
                    task.message_post(
                        body=message_body,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
        
        result = super(TaskManagement, self).write(vals)
        
        # Subscribe new assigned user
        if 'user_id' in vals:
            for task in self:
                if task.user_id:
                    task.message_subscribe(partner_ids=[task.user_id.partner_id.id])
        
        return result
    
    def copy(self, default=None):
        if default is None:
            default = {}
        if not default.get('name'):
            default['name'] = _('%s (Copy)', self.name)
        return super(TaskManagement, self).copy(default)
    
    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_task_as_done'):
            stage_done = self.env['task.stage'].search([('stage_type', '=', 'done')], limit=1)
            if stage_done:
                self.stage_id = stage_done
        return super(TaskManagement, self).message_post(**kwargs)
    
    def _send_overdue_notifications(self):
        """Send overdue notifications for tasks"""
        template = self.env.ref('task_management.email_template_task_overdue', raise_if_not_found=False)
        if not template:
            return
            
        for task in self:
            template.send_mail(task.id, force_send=True)
            task.message_post(
                body=_('Task is overdue.  Notification sent to %s') % task.user_id.name,
                message_type='notification',
            )

    def get_time_tracking_summary(self):
        """Get detailed time tracking summary for the task"""
        self.ensure_one()
        
        # Group timesheets by subtask
        subtask_times = {}
        for timesheet in self.timesheet_ids:
            subtask_key = timesheet.subtask_id.id if timesheet.subtask_id else 0
            if subtask_key not in subtask_times:
                subtask_times[subtask_key] = {
                    'name': timesheet.subtask_id.name if timesheet.subtask_id else 'Other Work',
                    'total_hours': 0,
                    'entries': []
                }
            subtask_times[subtask_key]['total_hours'] += timesheet.unit_amount
            subtask_times[subtask_key]['entries'].append({
                'date': timesheet.date,
                'user': timesheet.user_id.name,
                'hours': timesheet.unit_amount
            })
        
        return {
            'high_level_estimate': {
                'planned': self.planned_hours,
                'spent': self.effective_hours,
                'remaining': self.remaining_hours,
            },
            'time_logs': {
                'total_planned': self.total_planned_hours_from_logs,
                'logged': self.total_logged_hours,
                'remaining': self.total_remaining_hours_from_logs,
                'by_subtask': subtask_times,
            }
        }
    
    def _recompute_task_category(self):
        """Recompute task_category for all records."""
        for task in self.search([]):
            task._compute_task_category()
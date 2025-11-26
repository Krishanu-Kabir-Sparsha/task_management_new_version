# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


class TaskTimesheetLine(models.Model):
    _name = 'task.timesheet.line'
    _description = 'Task Time Log Entry'
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Html(
        string='Work Description',
        required=True,
        sanitize=True,
        help='Detailed description with rich text formatting'
    )
    
    task_id = fields.Many2one(
        'task.management',
        string='Task',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # CHANGED: Now REQUIRED with create option
    subtask_id = fields.Many2one(
        'task.subtask',
        string='Subtask',
        required=True,  # NOW REQUIRED
        domain="[('parent_task_id', '=', task_id)]",
        help='Select the specific subtask you worked on'
    )
    
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user
    )
    
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today
    )
    
    # NEW: Status field
    status = fields.Selection([
        ('in_progress', 'In Progress'),
        ('in_review', 'In Review'),
        ('done', 'Done')
    ], string='Status', default='in_progress', required=True, tracking=True)
    
    # NEW: Planned hours per time log entry
    planned_hours = fields.Float(
        string='Planned Time',
        default=0.0,
        help='Planned hours for this specific work entry'
    )
    
    # Time spent (renamed for clarity)
    unit_amount = fields.Float(
        string='Actual Time Logged',
        required=True,
        default=0.0,
        help='Time spent in decimal hours (e.g., 1.5 for 1h 30m)'
    )
    
    # NEW: Remaining hours (computed per entry)
    remaining_hours = fields.Float(
        string='Remaining',
        compute='_compute_remaining_hours',
        store=True,
        help='Remaining hours = Planned - Actual for this entry'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    # Task related fields for filtering/reporting
    task_type = fields.Selection(
        related='task_id.task_type',
        string='Task Type',
        store=True
    )
    
    task_stage_id = fields.Many2one(
        related='task_id.stage_id',
        string='Task Stage',
        store=True
    )
    
    @api.depends('planned_hours', 'unit_amount')
    def _compute_remaining_hours(self):
        """Calculate remaining hours per entry"""
        for record in self:
            record.remaining_hours = record.planned_hours - record.unit_amount
    
    @api.onchange('subtask_id')
    def _onchange_subtask_id(self):
        """Auto-fill description when subtask is selected"""
        if self.subtask_id and not self.name:
            self.name = f"<p>Worked on: <strong>{self.subtask_id.name}</strong></p>"
    
    @api.onchange('date')
    def _onchange_date(self):
        """Validate date when changed"""
        today = fields.Date.today()
        if self.date and self.date > today:
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _('You are selecting a future date. Time logs should typically be for past work.')
                }
            }
    
    @api.constrains('unit_amount')
    def _check_unit_amount(self):
        """Validate duration is positive"""
        for record in self:
            if record.unit_amount <= 0:
                raise ValidationError(_('Actual Time Logged must be greater than 0 hours.'))
    
    @api.constrains('planned_hours')
    def _check_planned_hours(self):
        """Validate planned hours is not negative"""
        for record in self:
            if record.planned_hours < 0:
                raise ValidationError(_('Planned Time cannot be negative.'))
    
    @api.constrains('date')
    def _check_date(self):
        """Validate time log date - no future dates"""
        today = fields.Date.today()
        for record in self:
            if record.date > today:
                raise ValidationError(_('You cannot log time for future dates'))
    
    @api.model
    def create(self, vals):
        """Override create to auto-fill description if needed"""
        if not vals.get('name') and vals.get('subtask_id'):
            subtask = self.env['task.subtask'].browse(vals['subtask_id'])
            vals['name'] = f"<p>Worked on: <strong>{subtask.name}</strong></p>"
        elif not vals.get('name'):
            vals['name'] = "<p>General work</p>"
        
        return super(TaskTimesheetLine, self).create(vals)
    
    def action_edit_time_log(self):
        """Open simplified form view for editing"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Edit Time Log'),
            'res_model': 'task.timesheet.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    @api.model
    def get_weekly_summary(self, user_id=None, date_from=None, date_to=None):
        """Get weekly time summary for reporting"""
        if not user_id:
            user_id = self.env.user.id
        if not date_from:
            today = fields.Date.today()
            date_from = today - timedelta(days=today.weekday())
        if not date_to:
            date_to = date_from + timedelta(days=6)
        
        domain = [
            ('user_id', '=', user_id),
            ('date', '>=', date_from),
            ('date', '<=', date_to)
        ]
        
        time_logs = self.search(domain)
        
        summary = {
            'total_hours': sum(time_logs.mapped('unit_amount')),
            'days_worked': len(set(time_logs.mapped('date'))),
            'tasks_worked': len(set(time_logs.mapped('task_id'))),
            'details': []
        }
        
        # Group by task
        for task in time_logs.mapped('task_id'):
            task_logs = time_logs.filtered(lambda l: l.task_id == task)
            summary['details'].append({
                'task': task.name,
                'hours': sum(task_logs.mapped('unit_amount')),
                'entries': len(task_logs)
            })
        
        return summary
    
    # REMOVED: Validation against task planned hours - now per-entry based
    
    @api.onchange('unit_amount', 'planned_hours')
    def _onchange_hours(self):
        """Show warning if actual exceeds planned for this entry"""
        if self.unit_amount and self.planned_hours:
            if self.unit_amount > self.planned_hours:
                return {
                    'warning': {
                        'title': _('⚠️ Exceeds Planned Time'),
                        'message': _(
                            'Actual Time Logged (%.2f hours) exceeds Planned Time (%.2f hours) for this entry.\n\n'
                            'Consider adjusting the planned time or actual time.'
                        ) % (self.unit_amount, self.planned_hours)
                    }
                }
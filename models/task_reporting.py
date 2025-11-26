# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _


class TaskReport(models.Model):
    """Task Analysis Report - Clean & Focused"""
    _name = 'task.report'
    _description = 'Task Analysis Report'
    _auto = False
    _rec_name = 'task_id'
    _order = 'date_start desc'

    # Core Task Information
    task_id = fields.Many2one('task.management', string='Task', readonly=True)
    name = fields.Char(string='Task Name', readonly=True)
    task_type = fields.Selection([
        ('individual', 'Individual Task'),
        ('team', 'Team Task')
    ], string='Task Type', readonly=True)
    
    # Assignment
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    team_id = fields.Many2one('task.team', string='Team', readonly=True)
    create_uid = fields.Many2one('res.users', string='Created By', readonly=True)
    
    # Status
    stage_id = fields.Many2one('task.stage', string='Stage', readonly=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority', readonly=True)
    is_closed = fields.Boolean(string='Is Closed', readonly=True)
    
    # Date
    date = fields.Date(string='Date', readonly=True)
    
    # Time Tracking - Tasks Level
    planned_hours = fields.Float(string='Planned Hours', readonly=True)
    effective_hours = fields.Float(string='Actual Hours', readonly=True)
    remaining_hours = fields.Float(string='Remaining Hours', readonly=True)
    
    # Time Tracking - Logs Level
    total_logged_hours = fields.Float(string='Logged Hours', readonly=True)
    
    # Performance
    task_performance = fields.Selection([
        ('over_estimated', 'Over Estimated'),
        ('on_track', 'On Track'),
        ('under_estimated', 'Under Estimated'),
        ('not_started', 'Not Started')
    ], string='Performance', readonly=True)
    
    # Subtasks
    subtask_count = fields.Integer(string='Total Subtasks', readonly=True)
    subtask_completed_count = fields.Integer(string='Completed Subtasks', readonly=True)
    
    # Computed Metrics
    is_overdue = fields.Boolean(string='Is Overdue', readonly=True)
    duration_days = fields.Integer(string='Duration (Days)', readonly=True)
    
    # Date Grouping
    date_month = fields.Char(string='Month', readonly=True)
    date_week = fields.Char(string='Week', readonly=True)
    date_year = fields.Char(string='Year', readonly=True)
    
    # Company
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        """Create optimized view for task analysis"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    t.id as id,
                    t.id as task_id,
                    t.name as name,
                    t.task_type as task_type,
                    t.user_id as user_id,
                    t.team_id as team_id,
                    t.create_uid as create_uid,
                    t.stage_id as stage_id,
                    t.priority as priority,
                    COALESCE(ts.is_closed, False) as is_closed,
                    t.date_start as date,
                    
                    -- Time Tracking
                    t.planned_hours as planned_hours,
                    t.effective_hours as effective_hours,
                    t.remaining_hours as remaining_hours,
                    t.total_logged_hours as total_logged_hours,
                    
                    -- Performance
                    t.task_performance as task_performance,
                    
                    -- Subtasks
                    t.subtask_count as subtask_count,
                    t.subtask_completed_count as subtask_completed_count,
                    
                    -- Computed
                    CASE
                        WHEN t.date_deadline < CURRENT_DATE AND COALESCE(ts.is_closed, False) = False 
                        THEN True ELSE False
                    END as is_overdue,
                    
                    CASE
                        WHEN t.date_start IS NOT NULL AND t.date_deadline IS NOT NULL 
                        THEN (t.date_deadline - t.date_start)
                        ELSE NULL
                    END as duration_days,
                    
                    -- Date Grouping
                    TO_CHAR(t.date_start, 'YYYY-MM') as date_month,
                    TO_CHAR(t.date_start, 'IYYY-IW') as date_week,
                    TO_CHAR(t.date_start, 'YYYY') as date_year,
                    
                    t.company_id as company_id
                    
                FROM task_management t
                LEFT JOIN task_stage ts ON t.stage_id = ts.id
                WHERE t.active = True
            )
        """ % self._table
        self.env.cr.execute(query)
    
    def action_open_task(self):
        """Open task form"""
        self.ensure_one()
        return {
            'name': self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'task.management',
            'res_id': self.task_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


class TimesheetReport(models.Model):
    """Time Log Summary Report - Clean & Focused"""
    _name = 'timesheet.report'
    _description = 'Time Log Summary'
    _auto = False
    _rec_name = 'id'
    _order = 'date desc'

    # Time Log Entry
    timesheet_id = fields.Many2one('task.timesheet.line', string='Time Log', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    
    # Status
    status = fields.Selection([
        ('in_progress', 'In Progress'),
        ('in_review', 'In Review'),
        ('done', 'Done')
    ], string='Status', readonly=True)
    
    # Time Tracking
    planned_hours = fields.Float(string='Planned Hours', readonly=True)
    unit_amount = fields.Float(string='Actual Hours', readonly=True)
    remaining_hours = fields.Float(string='Remaining Hours', readonly=True)
    
    # Assignment
    user_id = fields.Many2one('res.users', string='Employee', readonly=True)
    
    # Task Context
    task_id = fields.Many2one('task.management', string='Task', readonly=True)
    task_name = fields.Char(string='Task Name', readonly=True)
    task_type = fields.Selection([
        ('individual', 'Individual Task'),
        ('team', 'Team Task')
    ], string='Task Type', readonly=True)
    
    # Subtask
    subtask_id = fields.Many2one('task.subtask', string='Subtask', readonly=True)
    subtask_name = fields.Char(string='Subtask Name', readonly=True)
    
    # Team
    team_id = fields.Many2one('task.team', string='Team', readonly=True)
    
    # Date Grouping
    date_month = fields.Char(string='Month', readonly=True)
    date_week = fields.Char(string='Week', readonly=True)
    date_year = fields.Char(string='Year', readonly=True)
    
    # Company
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        """Create optimized view for time log analysis"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        query = """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    tl.id as id,
                    tl.id as timesheet_id,
                    tl.date as date,
                    tl.status as status,
                    tl.planned_hours as planned_hours,
                    tl.unit_amount as unit_amount,
                    tl.remaining_hours as remaining_hours,
                    tl.user_id as user_id,
                    
                    -- Task Context
                    tl.task_id as task_id,
                    t.name as task_name,
                    t.task_type as task_type,
                    
                    -- Subtask
                    tl.subtask_id as subtask_id,
                    ts.name as subtask_name,
                    
                    -- Team
                    t.team_id as team_id,
                    
                    -- Date Grouping
                    TO_CHAR(tl.date, 'YYYY-MM') as date_month,
                    TO_CHAR(tl.date, 'IYYY-IW') as date_week,
                    TO_CHAR(tl.date, 'YYYY') as date_year,
                    
                    tl.company_id as company_id
                    
                FROM task_timesheet_line tl
                LEFT JOIN task_management t ON tl.task_id = t.id
                LEFT JOIN task_subtask ts ON tl.subtask_id = ts.id
            )
        """ % self._table
        self.env.cr.execute(query)
    
    def action_open_task(self):
        """Open task form"""
        self.ensure_one()
        return {
            'name': self.task_name,
            'type': 'ir.actions.act_window',
            'res_model': 'task.management',
            'res_id': self.task_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
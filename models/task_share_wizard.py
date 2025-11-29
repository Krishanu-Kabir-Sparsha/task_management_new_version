# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TaskShareWizard(models.TransientModel):
    _name = 'task.share.wizard'
    _description = 'Task Share Wizard'

    task_id = fields.Many2one('task.management', string='Task', required=True)
    user_ids = fields.Many2many('res.users', string='Share With Users', domain="[('share', '=', False)]")
    message = fields.Text(string='Message', default='I want to share this task with you')

    def action_share(self):
        """Share task with selected users"""
        self.ensure_one()
        if self.user_ids:
            partner_ids = self.user_ids.mapped('partner_id').ids
            self.task_id.message_subscribe(partner_ids=partner_ids)
            body = f"<p>{self.message}</p><p><a href='/web#id={self.task_id.id}&model=task.management&view_type=form'>View Task</a></p>"
            self.task_id.message_post(
                body=body,
                subject=f'Task Shared: {self.task_id.name}',
                partner_ids=partner_ids,
                message_type='notification',
            )
        return {'type': 'ir.actions.act_window_close'}
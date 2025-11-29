# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TaskCoverImageWizard(models.TransientModel):
    _name = 'task.cover.image.wizard'
    _description = 'Task Cover Image Wizard'

    task_id = fields.Many2one('task.management', string='Task', required=True)
    cover_image = fields.Binary(string='Cover Image', required=True)
    cover_image_filename = fields.Char(string='Filename')

    def action_set_cover(self):
        """Set cover image for task"""
        self.ensure_one()
        
        if not self.cover_image:
            return {'type': 'ir.actions.act_window_close'}
        
        # Delete old cover image
        if self.task_id.displayed_image_id:
            old_attachment = self.task_id.displayed_image_id
            self.task_id.displayed_image_id = False
            old_attachment.unlink()
        
        # Create new attachment
        attachment = self.env['ir.attachment'].create({
            'name': self.cover_image_filename or 'cover_image.png',
            'datas': self.cover_image,
            'res_model': 'task.management',
            'res_id': self.task_id.id,
            'public': True,
        })
        
        # Link to task
        self.task_id.displayed_image_id = attachment.id
        
        return {'type': 'ir.actions.act_window_close'}
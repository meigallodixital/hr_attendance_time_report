# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from datetime import timedelta, datetime
from odoo import api, fields, models

class HrAttendanceTimeWizard(models.TransientModel):
    _name = 'hr.attendance.time.wizard'
    _description = 'HR Attendances Time Wizard'

    employee_ids = fields.Many2many('hr.employee')
    date_start = fields.Date(default=lambda self: self.default_date_start())
    date_end = fields.Date(default=lambda self: self.default_date_end())
    rounded = fields.Boolean(default=False)
    not_worked = fields.Boolean(default=True)
    category_ids = fields.Many2many(
        'hr.employee.category', string='Tag'
    )

    @api.model
    def default_date_start(self):
        return self.default_date_end().replace(day=1)

    @api.model
    def default_date_end(self):
        first_day = fields.Date.today().replace(day=1)
        return first_day - timedelta(1)

    @api.multi
    def get_report(self):
        data = {
            'model': self._name,
            'ids': self.ids,
            'form': {
                'employee_ids': self.employee_ids.ids,
                'date_start': self.date_start,
                'date_end': self.date_end,
                'rounded': self.rounded,
                'not_worked': self.not_worked,
                'category_ids': self.category_ids.ids
            }
        }

        return self.env.ref(
            'hr_attendance_time_report.action_hr_attendance_time_report'
            ).report_action(
                self,
                data=data
            )

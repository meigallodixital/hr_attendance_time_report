
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import collections
from datetime import datetime, timedelta, date
import pytz
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import models, api, _
from odoo.exceptions import ValidationError


class HrAttendanceTimeReport(models.AbstractModel):
    _name = 'report.hr_attendance_time_report.hr_attendance_time_report'

    with_seconds = False

    def daterange(self, start_date, end_date):
        if start_date == end_date:
            yield start_date.strftime('%d/%m/%Y')

        for day in range(int((end_date - start_date).days) + 1):
            new_date = start_date + timedelta(day)
            yield new_date.strftime('%d/%m/%Y')

    def float_to_hour(self, hours):
        seconds = int(hours * 3600)
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if self.with_seconds:
            return "%02d:%02d:%02d" % (hours, mins, secs)
        else:
            return "%02d:%02d" % (hours, mins)

    def group_attendances(self, attendances, actual_timezone):
        attendance_items = {}
        for attendance in attendances:
            check_in = attendance.check_in.astimezone(actual_timezone)
            check_out = attendance.check_out.astimezone(actual_timezone)
            check_in_date = check_in.strftime('%d/%m/%Y')
            attendance_exists = attendance_items.get(check_in_date)
            if attendance_exists:
                attendance_items[check_in_date]['check_ins'].append(
                    check_in.time())
                attendance_items[check_in_date]['check_outs'].append(
                    check_out.time())
                attendance_items[check_in_date]['justify_float'] += attendance.worked_hours
                attendance_items[check_in_date]['justify'] = self.float_to_hour(
                    attendance_items[check_in_date]['justify_float'])
                attendance_items[check_in_date]['delta'] = self.float_to_hour(
                    attendance_items[check_in_date]['justify_float'] - attendance.theoretical_hours)
            else:
                attendance_items.update({
                    check_in_date: {
                        'check_ins': [check_in.time()],
                        'check_outs': [check_out.time()],
                        'check_in_date': check_out.date(),
                        'check_out_date': check_out.date(),
                        'justify': self.float_to_hour(attendance.worked_hours),
                        'justify_float': attendance.worked_hours,
                        'theoretical': self.float_to_hour(attendance.theoretical_hours),
                        'theoretical_float': attendance.theoretical_hours,
                        'type':  _("attendance")
                    }
                })
                # Update attendance_exists to update delta value
                attendance_exists = attendance_items.get(check_in_date)

            if attendance_items[check_in_date]['justify_float'] > attendance.theoretical_hours:
                attendance_items[check_in_date]['delta'] = self.float_to_hour(
                    attendance_items[check_in_date]['justify_float'] - attendance.theoretical_hours)
            else:
                attendance_items[check_in_date]['delta'] = '-' + self.float_to_hour(
                    attendance.theoretical_hours - attendance_items[check_in_date]['justify_float'])

        return attendance_items

    def group_leaves(self, leaves, actual_timezone):
        leave_items = {}
        for leave in leaves:
            date_from = leave.date_from.astimezone(actual_timezone).date()
            date_to = leave.date_to.astimezone(actual_timezone).date()
            for day in self.daterange(date_from, date_to):
                item = {
                    day: {
                        'check_in': leave.date_from.astimezone(actual_timezone).time(),
                        'check_out': leave.date_to.astimezone(actual_timezone).time(),
                        'check_in_date': day,
                        'check_out_date': day,
                        'justify': "",
                        'justify_float': "",
                        'theoretical': "",
                        'type': leave.holiday_status_id.name
                    }
                }
                if leave.name:
                    item[day]['type'] = leave.name

                leave_items.update(item)

        return leave_items

    def month_totals(self, month_justify, month_theoretical):
        item = {
            'type': 'Total',
            'date_in': "",
            'check1': "",
            'check2': "",
            'justify': self.float_to_hour(month_justify),
            'theoretical': self.float_to_hour(month_theoretical)
        }
        if month_justify > month_theoretical:
            item['delta'] = self.float_to_hour(
                month_justify - month_theoretical)
        else:
            item['delta'] = '-' + self.float_to_hour(
                month_theoretical - month_justify)
        return item

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = []
        employees = []
        employee_search = []

        # Set seconds on report
        self.with_seconds = data['form']['rounded']

        if data['form']['employee_ids']:
            employee_search.append(
                ('id', "in", data['form']['employee_ids'])
            )

        if data['form']['category_ids']:
            employee_search.append(
                ('category_ids', 'in', data['form']['category_ids'])
            )

        employees = self.env['hr.employee'].search(
            employee_search, order="name asc")
        date_start = datetime.strptime(
            data['form']['date_start'], DEFAULT_SERVER_DATE_FORMAT).date()
        date_end = datetime.strptime(
            data['form']['date_end'], DEFAULT_SERVER_DATE_FORMAT).date()
        today = date.today()

        if date_end > today:
            # Today checkout can not exist yet
            date_end = today-datetime.timedelta(days=1)

        # Report data
        items = collections.OrderedDict()

        for employee in employees:
            # Reset employee data
            actual_timezone = pytz.timezone(
                employee.resource_id.calendar_id.tz)
            attendance_items = {}
            leaves_items = {}
            totals = {}

            # Get employees calendars
            sql = """
            select distinct hec.date_start,
                hec.date_end,
                hec.employee_id,
                rc.hours_per_day,
                rc.tz,
                rc.name,
                rca.dayofweek
                from hr_employee_calendar hec 
                join resource_calendar rc on rc.id = hec.calendar_id
                join resource_calendar_attendance rca on rca.calendar_id = hec.calendar_id
                where hec.employee_id = {}
            """
            self.env.cr.execute(sql.format(employee.id,))
            calendars = self.env.cr.dictfetchall()

            # Get attendances
            attendances = self.env['hr.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', date_start),
                ('check_out', '<=', date_end),
            ], order="check_in asc")
            attendance_items = self.group_attendances(
                attendances, actual_timezone)

            # Get leaves
            leaves = self.env['hr.leave'].search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                '|', '&', ('date_from', '>=',
                           date_start), ('date_from', '<=', date_end),
                '&', ('date_to', '>=', date_start), ('date_to', '<=', date_end)
            ], order="date_from asc")
            leaves_items = self.group_leaves(leaves, actual_timezone)

            # Check employes first day
            first_day = date_start
            if not employee.theoretical_hours_start_date:
                raise ValidationError(
                    _("Employee {} has not theoretical start date").format(
                        employee.name)
                    )

            if date_start < employee.theoretical_hours_start_date:
                first_day = employee.theoretical_hours_start_date

            month = first_day.month
            items[month] = []
            totals[month] = {}
            month_theoretical = 0.0
            month_justify = 0.0

            for day in self.daterange(first_day, date_end):
                # Check if month changes
                day_date = datetime.strptime(
                    day, '%d/%m/%Y').date()

                if month != day_date.month:
                    item = self.month_totals(month_justify, month_theoretical)
                    totals[month] = item
                    month = day_date.month
                    items[month] = []
                    month_theoretical = 0.0
                    month_justify = 0.0

                attendance = attendance_items.get(day)
                leave = leaves_items.get(day)
                holiday = self.env['hr.holidays.public'].is_public_holiday(
                    day_date, employee.id)

                if attendance:
                    month_theoretical += attendance.get('theoretical_float')
                    month_justify += attendance.get('justify_float')
                    item = {
                        'type': attendance.get('type'),
                        'date_in': day,
                        'check1': "{} - {}".format(
                            attendance.get('check_ins')[0],
                            attendance.get('check_outs')[0]),
                        'check2': "",
                        'justify': attendance.get('justify'),
                        'theoretical': attendance.get('theoretical'),
                        'delta': attendance.get('delta')
                    }

                    if len(attendance.get('check_ins')) > 1:
                        item['check2'] = "{} - {}".format(
                            attendance.get('check_ins')[1],
                            attendance.get('check_outs')[1])

                    # Set data and update previous date
                    items[month].append(item)

                if leave:
                    item = {
                        'type': leave.get('type'),
                        'date_in': day,
                        'check1': "",
                        'check2': "",
                        'justify': "",
                        'theoretical': "",
                        'delta': ""
                    }
                    items[month].append(item)

                if holiday:
                    holidays = self.env['hr.holidays.public'].get_holidays_list(
                        day_date.year, employee.id)
                    holiday_actual = holidays.filtered(
                        lambda r: r.date == day_date
                    )
                    item = {
                        'type': holiday_actual[0].name,
                        'date_in': day,
                        'check1': "",
                        'check2': "",
                        'justify': "",
                        'theoretical': "",
                        'delta': ""
                    }
                    items[month].append(item)

                if not attendance and not leave and not holiday \
                    and data['form']['not_worked']:
                    # Check if this days is a workin day
                    day_week = day_date.weekday()
                    exist = [
                        dw['dayofweek'] for dw in calendars \
                            if int(dw['dayofweek']) == day_week \
                            and (not dw['date_start'] or day_date >= dw['date_start']) \
                            and (not dw['date_end'] or day_date <= dw['date_end'])
                        ]
                    if not exist:
                        day_type = _('Not workin day')
                    else:
                        day_type = _('Day off')

                    item = {
                        'type': day_type,
                        'date_in': day,
                        'check1': "",
                        'check2': "",
                        'justify': "",
                        'theoretical': "",
                        'delta': ""
                    }
                    items[month].append(item)

            # Last totals
            item = self.month_totals(month_justify, month_theoretical)
            totals[month] = item
            month_theoretical = 0.0
            month_justify = 0.0

            docs.append({
                'name': employee.name,
                'attendances': items,
                'totals': totals
            })

        return {
            'doc_ids': [],
            'doc_model': data['model'],
            'date_start': date_start.strftime('%d/%m/%Y'),
            'date_end': date_end.strftime('%d/%m/%Y'),
            'docs': docs,
        }

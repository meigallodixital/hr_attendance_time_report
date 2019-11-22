# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "HR Attendance Time Report",
    "version": "12.0.1.0.0",
    "author": "Gonzalo González Domínguez",
    "website": "https://github.com/oca/hr",
    "license": "AGPL-3",
    "category": "Human Resources",
    "depends": ["hr", "hr_attendance", "hr_attendance_report_theoretical_time", "hr_employee_calendar_planning"],
    "data": [
        "reports/hr_attendance_time_report.xml",
        "wizard/hr_attendance_time_wizard.xml"
    ],
    'installable': True
}

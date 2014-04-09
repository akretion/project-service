# -*- encoding: utf-8 -*-
###############################################################################
#                                                                             #
#   project_invoicing for OpenERP                                             #
#   Copyright (C) 2012 Akretion Benoît GUILLOT <benoit.guillot@akretion.com>  #
#                                                                             #
#   This program is free software: you can redistribute it and/or modify      #
#   it under the terms of the GNU Affero General Public License as            #
#   published by the Free Software Foundation, either version 3 of the        #
#   License, or (at your option) any later version.                           #
#                                                                             #
#   This program is distributed in the hope that it will be useful,           #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU Affero General Public License for more details.                       #
#                                                                             #
#   You should have received a copy of the GNU Affero General Public License  #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
###############################################################################



{
    'name': 'project_invoicing',
    'version': '0.1',
    'category': 'Generic Modules/Others',
    'license': 'AGPL-3',
    'description': """empty""",
    'author': 'Akretion',
    'website': 'http://www.akretion.com/',
    'depends': [
        'hr_timesheet_task',
        'project_typology',
    ], 
    'init_xml': [],
    'update_xml': [ 
           'project_view.xml',
           'invoice_view.xml',
           'wizard/project_task_invoice_create_view.xml',
           'wizard/hr_timesheet_invoice_create_view.xml',
    ],
    'demo': [
       'project_demo.xml', 
    ],
    'installable': True,
    'active': False,
}


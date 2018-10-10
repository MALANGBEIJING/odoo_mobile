# -*- coding: utf-8 -*-
import jinja2, sys, os
import  openerp
from openerp.addons.web.controllers.main import ensure_db
from openerp import http
from openerp.http import request
import copy
import datetime
from openerp.tools import float_round, SUPERUSER_ID
import simplejson
import os
from dateutil.relativedelta import relativedelta
ISODATEFORMAT = '%Y-%m-%d'
ISODATETIMEFORMAT = "%Y-%m-%d %H:%M:%S"
MOBILEDATETIMEFORMAT = "%Y-%m-%d %H:%M"
view_type = {
    'tree': 'Tree',
    'card': 'OdooCard',
    'bar': 'OdooCard'
}

if hasattr(sys, 'frozen'):
    # When running on compiled windows binary, we don't have access to package loader.
    path = os.path.realpath(os.path.join(os.path.dirname(__file__), '..', 'html'))
    loader = jinja2.FileSystemLoader(path)
else:
    loader = jinja2.PackageLoader('openerp.addons.mobile', "html")

env = jinja2.Environment('<%', '%>', '${', '}', '%', loader=loader, autoescape=True)


class MobileController(http.Controller):
    @http.route('/odoo/mobile', auth='public')
    def odoo_mobile(self, **kwargs):
        """
        odoo  手机端初始化页面
        :param kwargs:
        :return:
        """

        template = env.get_template("index.html")
        return template.render()

    @http.route('/odoo/mobile/get/all/grid_data', auth='mobile', type='http', method=['GET'])
    def get_all_grid_data(self, **args):
        """
        获取配置信生成手机端的前端的视图
        :param args:
        :return:
        """
        # TODO 要用上 权限的设定等设置
        cr, context, pool = request.cr, request.context, request.registry
        uid = request.session.get('uid') or SUPERUSER_ID
        grid_obj = pool.get('mobile.grid')
        allGridData = {}
        grid_ids = grid_obj.search(cr, uid, [], context=context)
        # 搜索所有九宫格的动作的定义（可以加用户组相关的信息)
        all_groups = pool.get('res.users').read(cr, uid, [uid], ['groups_id'], context=context)[0]['groups_id']
        for grid in grid_obj.browse(cr, uid, grid_ids, context=context):
            if grid.group_ids and len([group.id for group in grid.group_ids if group.id in all_groups]) == 0:
                continue
            allGridData.setdefault(grid.label_id, []).append({
                'title': grid.title,
                'actionId': grid.mobile_action_id.id,
                'image': 'data:image/png;base64,' + grid.image  # 图片信息直接读取返回前端用base64
            })
        gridList = [{'groupTitle': label.name, 'sequence': label.sequence,
                     'gridCols': 4, 'gridRow': row} for label, row in allGridData.iteritems()]
        gridList = sorted(gridList, key=lambda grid: grid.get('sequence'))
        return simplejson.dumps(gridList)

    @http.route('/odoo/mobile/get/action/views', auth='mobile', type='http', method=['GET'])
    def get_action_views(self, **args):
        """
        返回对应的grid action 信息 返回odoo对应的 记录搜索的一些重要信息
        :param args:
        :return:
        """
        # todo 还需要进一步的完善很多参数没用上
        action_id = int(args.get('actionId', 0))
        cr, context, pool = request.cr, request.context, request.registry
        uid = request.session.get('uid') or SUPERUSER_ID
        all_groups = pool.get('res.users').read(cr, uid, [uid], ['groups_id'], context=context)[0]['groups_id']
        action_row = pool.get('mobile.action').browse(cr, uid, action_id, context=context)
        views_data = [{'title': domain.name,
                       'sequence': domain.sequence,
                       'badge': self.get_bage_text(pool, cr, uid, action_row.model_id.name,
                                                  domain.domain, domain.need_badge, context=context),
                       'domain': domain.domain} for domain in action_row.mobile_view_id.domain_ids
                      if domain.group_ids and
                      len([group.id for group in domain.group_ids if group.id in all_groups]) != 0 or not domain.group_ids]
        sorted(views_data, key=lambda view: view.get('sequence'))
        return_val = {
            'title': action_row.name,
            'modelID': action_row.model_id.id,
            'view_id': action_row.mobile_view_id.id,
            'noForm': action_row.mobile_view_id.no_form,
            'model': action_row.model_id.model,
            'limit': action_row.limit or 6,  # 重要，
            'offset': action_row.offset or 6,
            'order': action_row.order or 'id DESC',
            'context': action_row.mobile_view_id.context,
            'viewsData': views_data,
            'view_type': view_type.get(action_row.mobile_view_id.view_type)
        }
        return simplejson.dumps(return_val)

    def get_bage_text(self, pool, cr, uid, mode_name, domain, need_badge, context=None):
        badge_num = 0
        user = pool.get('res.users').browse(cr, uid, uid, context=context)
        if need_badge:
            badge_num = pool.get(mode_name).search_count(cr, uid, eval(domain), context=context)
        return badge_num

    @http.route('/odoo/mobile/get/list/view/data', auth='mobile', type='http', method=['GET'])
    def get_action_form_pre_view(self, **args):
        """
        列表视图的显示的数据的信息
        :param args:
        :return:
        """
        cr, context, pool = request.cr, request.context, request.registry
        action_id = int(args.get('actionId', '0'))
        offset = int(args.get('offset', '0'))
        limit = int(args.get('limit', '0'))
        uid = request.session.get('uid') or SUPERUSER_ID
        user = pool.get('res.users').browse(cr, uid, uid, context=context)
        order = args.get('order', 'id DESC')
        domain = eval(args.get('domain', '[]'))
        view_id = int(args.get('view_id', '0'))
        if not args.get('model'):
            return simplejson.dumps({})
        model_name = args.get('model')
        if not model_name:
            return simplejson.dumps({})
        record_ids = pool.get(model_name).search(cr, uid, domain, offset=offset, limit=limit, order=order,
                                                 context=context)
        return_val = []
        for view_row in pool.get('mobile.view').browse(cr, uid, view_id, context=context):
            return_val = self.get_view_type_function(view_row.view_type)(pool, cr, uid, view_row,
                                                                         record_ids, model_name, context=context)
            return simplejson.dumps(return_val)
        return simplejson.dumps(return_val)

    def get_view_type_function(self, type):
        type_dict = {
            'card': self.get_card_view_data,
            'tree': self.get_tree_view_data,
            # 'bar': self.get_bar_view_data,
        }
        return type_dict.get(type)

    def get_all_field_setting(self, field):
        """
        获取字段上对应的默认的前端可能有用的信息
        :param field:
        :return:
        """
        return {
            'title': field.ir_field.field_description,
            'type': field.field_type,
            'is_show_edit_form': field.is_show_edit_form,
            'is_show_form_tree': field.is_show_form_tree,
            'value': '',
            'domain': False,
            'required': field.required,
            'readonly': field.readonly,
            'invisible': field.invisible,
            'name': field.ir_field.name,
        }

    def get_tree_view_data(self, pool, cr, uid, view_row, record_ids, model_name, context=None):
        """
        button 的显示的domain 可以添加参数 ，可以添加 user 及相关的信息作为条件
        """
        return_val = []
        all_field = []
        all_groups = pool.get('res.users').read(cr, uid, [uid], ['groups_id'], context=context)[0]['groups_id']
        for field in view_row.mobile_field_ids:
            if field.group_ids and len([group.id for group in field.group_ids if group.id in all_groups]) == 0:
                continue
            all_field.append(self.get_all_field_setting(field))
        user = pool.get('res.users').browse(cr, uid, uid, context=context)
        for button in view_row.button_ids:
            domain = eval(button.show_condition or '[]') + [('id', 'in', record_ids)]
            mode_ids = pool.get(model_name).search(cr, uid, domain, context=context)
            if button.group_ids and len([group.id for group in button.group_ids if group.id in all_groups]) == 0:
                continue
            all_field.append({
                'title': button.name,
                'type': 'button',
                'style': button.style,
                'value': button.button_method,
                'model': model_name,
                'ids': mode_ids,
            })
        for record in pool.get(model_name).browse(cr, uid, record_ids, context=context):
            new_fields = copy.deepcopy(all_field)
            [field.update(self.card_show_val(uid, record, field, context=context, user=user))
             for field in new_fields]
            tree_val = {
                'title': record['display_name'],
                'id': record.id,
                'meta': new_fields
            }
            return_val.append(tree_val)
        return return_val

    def get_card_view_data(self, pool, cr, uid, view_row, record_ids, model_name, context=None):
        """

        :param pool:
        :param cr:
        :param uid:
        :param view_row:
        :param record_ids:
        :param model_name:
        :param context:
        :return:
        """
        return_val = []
        all_field = []
        all_groups = pool.get('res.users').read(cr, uid, [uid], ['groups_id'], context=context)[0]['groups_id']
        for field in view_row.mobile_field_ids:
            if field.group_ids and len([group.id for group in field.group_ids if group.id in all_groups]) == 0:
                continue
            all_field.append(self.get_all_field_setting(field))
        user = pool.get('res.users').browse(cr, uid, uid, context=context)
        for button in view_row.button_ids:
            domain = eval(button.show_condition or '[]') + [('id', 'in', record_ids)]
            mode_ids = pool.get(model_name).search(cr, uid, domain, context=context)
            if button.group_ids and len([group.id for group in button.group_ids if group.id in all_groups]) == 0:
                continue
            all_field.append({
                'title': button.name,
                'type': 'button',
                'style': button.style,
                'value': button.button_method,
                'model': model_name,
                'ids': mode_ids,
                'invisible': button.show_condition
            })
        for record in pool.get(model_name).browse(cr, uid, record_ids, context=context):
            new_fields = copy.deepcopy(all_field)
            [field.update(self.card_show_val(uid, record, field, context=context, user=user))
             for field in new_fields]
            return_val.append({'fieldVals': new_fields, 'id': record.id})
        return return_val

    def card_show_val(self, uid, record, field, context=None, user=None):
        """
        :param uid:
        :param record:
        :param field:
        :param context:
        :return:
        """
        return_value = {}
        return_value.update({
            'invisible': eval(field.get('invisible') or 'False'),
            'readonly': eval(field.get('readonly') or 'False'),
            'required': eval(field.get('required') or 'False'),
        })
        if field.get('type') not in ('button', 'one2many', 'many2one'):
            return_value.update({'value': self.card_field_type_get_val(field, record, context=context)})
        if field.get('type') == 'many2one':
            options = self.card_field_type_get_val(field, record, context=context)
            return_value.update({'options': self.card_field_type_get_val(field, record, context=context),
                                 'value': options and options[0] and options[0].get('key'),
                                 'domain': eval(field.get('domain') or '[]')
                                 })
        elif field.get('type') == 'many2many':
            options = self.card_field_type_get_val(field, record, context=context)
            return_value.update({'options': options,
                                 'value': [option.get('key') for option in options],
                                 'domain': str(eval(field.get('domain') or '[]'))
                                 })
        elif field.get('type') == 'button':
            return_value.update(
                {'invisible': False if record['id'] in field.get('ids') else True})
        elif field.get('type') == 'one2many':
            value, ids = self.get_show_tree_one2many(uid, record, field, context=context, user=user)
            return_value.update({'value': value,
                                 'ids': ids,
                                 'table': self.get_record_one2many(uid, record, field,
                                                                   context=dict(context, **{'table': True}), user=user)
                                 })
        elif field.get('type') == 'selection':
            value = self.card_field_type_get_val(field, record, context=context)
            return_value.update({'value': value,
                                 'options': [{'key': value[0], 'value': value[1]} for value in
                                             record._fields[field.get('name')].selection]
                                 })

        return return_value

    def get_show_tree_one2many(self, uid, record, field, context=None, user=None):
        """
        构造出 one2many手机端所需要的数据结构
        :param uid:
        :param record:
        :param field:
        :param context:
        :return:
        """
        all_tree_row, table_body, line_ids = [], [], []
        many_field = field.get('many_field', [])

        if not (many_field and field.get('name')):
            return '', ''
        for line in record[field.get('name')]:
            line_ids.append(line['id'])
            new_fields = copy.deepcopy(many_field)
            [field.update(self.card_show_val(uid, line, field, context=dict(context, **{'table': True}), user=user))
             for field in new_fields]
            tree_val = {
                'title': line['display_name'],
                'id': line.id,
                'meta': new_fields
            }
            all_tree_row.append(tree_val)
        return all_tree_row, line_ids

    def card_field_type_get_val(self, field, record, context=None):
        """
        展示字段信息的处理
        :param field:
        :param record:
        :param context:
        :return:
        """
        # TODO 进一步的完善字段的显示 添加更多的类型 或者有更多的展示的
        type = field.get('type')
        value = record[field.get('name')]
        if not value:
            return ''
        if type in ('char', 'text', 'boolean', 'integer'):
            return value
        elif type == 'many2one':

            if value and value.name_get():
                name = value.name_get()
                return [{'key': name[0][0], 'value': name[0][1]}]
        elif type == 'date':
            date_obj = datetime.datetime.strptime(value, ISODATEFORMAT)
            return (date_obj + relativedelta(hours=8)).strftime(ISODATEFORMAT)
        elif type == 'datetime':
            date_obj = datetime.datetime.strptime(value, ISODATETIMEFORMAT)
            return (date_obj + relativedelta(hours=8)).strftime(MOBILEDATETIMEFORMAT)
        elif type == 'float':
            return float_round(value, precision_digits=2)
        elif type == 'selection':
            return value
        elif type == 'many2many':
            if value and value.name_get():
                names = value.name_get()
                return [{'key': name[0], 'value': name[1]} for name in names]
        return ''

    def get_record_one2many(self, uid, record, field, context=None, user=None):
        """
        这个是设计前期的一个方案，估计要废弃 。查看的from视图的table
        :param uid:
        :param record:
        :param field:
        :param context:
        :return:
        """
        table_header, table_body = [], []
        many_field = field.get('many_field', [])
        if not (many_field and field.get('name')):
            return ''
        for son_field in many_field:
            table_header.append(son_field.get('title'))
        for line in record[field.get('name')]:
            new_fields = copy.deepcopy(many_field)
            [field.update(self.card_show_val(uid, line, field, context=context, user=user))
             for field in new_fields]
            table_body.append(new_fields)
        return {'tableTh': table_header, 'tableBody': table_body}

    # /odoo/button/method
    @http.route('/odoo/mobile/button/method', auth='mobile', type='http', method=['GET'])
    def mobile_button_method(self, **args):
        """
        odoo前端调用odoo自带的方法
        :param args:
        :return:
        """
        cr, context, pool = request.cr, request.context, request.registry
        uid = request.session.get('uid') or SUPERUSER_ID
        model = args.get('model')
        method = args.get('method')
        ids = int(args.get('ids'))
        model_obj = pool.get(model)
        if model_obj and hasattr(model_obj, method) and ids:
            try:
                getattr(model_obj, method)(cr, uid, ids, context=context)
                return simplejson.dumps({'success': True})
            except Exception as exc:
                if isinstance(exc, basestring):
                    return simplejson.dumps({'success': False, 'errMsg': u'%s' % exc})
                if exc and hasattr(exc, 'value'):
                    return simplejson.dumps({'success': False, 'errMsg': u'%s' % exc.value})
                if exc and hasattr(exc, 'message') and hasattr(exc, 'diag'):
                    return simplejson.dumps({'success': False, 'errMsg': u'%s' % exc.diag.message_primary})
                elif exc and hasattr(exc, 'message'):
                    return simplejson.dumps({'success': False, 'errMsg': u'%s' % exc.message})
                elif exc and hasattr(exc, dict):
                    return simplejson.dumps({'success': False, 'errMsg': u'%s' % exc.get('message')})

    def get_many_field_value(self, field):
        """
        many2one字段的进一步的处理
        :param field:
        :return:
        """
        field_value = self.get_all_field_setting(field)
        if field.field_type == 'many2one':
            field_value.update({'model': field.ir_field.relation, 'domain': field.domain, 'options': []})
        return field_value

    def set_default_val(self, pool, cr, uid, field_value, default_val):
        """
        1。获取字段默认值，这些默认字段尽量都要配置到手机端的视图上
        2。必须加到视图上，不然这些默认值也不会生效的。（应该是的）
        :param pool:
        :param cr:
        :param uid:
        :param field_value:
        :param default_val:
        :return:
        """
        # TODO 默认值尽量手机端页面上没有配置也要正常的写入数据库
        if default_val.get(field_value.get('name')):
            if field_value.get('type') == 'many2one':
                options = pool.get(field_value.get('model')).name_get(cr, uid, default_val.get(field_value.get('name')),
                                                                      context=None)
                return {'value': default_val.get(field_value.get('name')),
                        'options': [{'key': option[0], 'value': option[1]} for option in options]}
            else:
                return {'value': default_val.get(field_value.get('name'))}
        return {}

    def get_form_view_data(self, pool, cr, uid, view_row, record_ids, model_name, context=None):
        """
        处理通过页面配置的form Tree 视图的
        :param pool:
        :param cr:
        :param uid:
        :param view_row:
        :param record_ids:
        :param model_name:
        :param context:
        :return:
        """
        all_field = []
        user = pool.get('res.users').browse(cr, uid, uid, context=context)
        default_val = pool.get(model_name).default_get(cr, uid, [field.ir_field.name for field
                                                                 in view_row.mobile_field_ids], context=context)
        all_groups = pool.get('res.users').read(cr, uid, [uid], ['groups_id'], context=context)[0]['groups_id']
        for field in view_row.mobile_field_ids:
            field_value = self.get_all_field_setting(field)
            if field.field_type == 'many2one':
                field_value.update({'model': field.ir_field.relation, 'domain': field.domain or []})
            if field.field_type == 'selection':
                field_value.update({'options': [{'key': value[0], 'value': value[1]} for value in
                                                pool.get(model_name)._fields[field_value.get('name')].selection]})
            if field.field_type == 'one2many':
                field_value.update({'many_field': [self.get_many_field_value(field) for field in field.many_field],
                                    'value': []})
            if field.field_type == 'many2many':
                field_value.update({'model': field.ir_field.relation, 'domain': field.domain or [],
                                    'value': []})

            field_value.update(self.set_default_val(pool, cr, uid, field_value, default_val))
            all_field.append(field_value)
        for button in view_row.button_ids:
            domain = eval(button.show_condition or '[]') + [('id', '=', record_ids)]
            mode_ids = pool.get(model_name).search(cr, uid, domain, context=context)
            all_field.append({
                'title': button.name,
                'type': 'button',
                'style': button.style,
                'value': button.button_method,
                'user_ids': [True for group in button.group_ids if group.id in all_groups],
                'model': model_name,
                'ids': mode_ids,
                'invisible': button.show_condition
            })
        for record in pool.get(model_name).browse(cr, uid, record_ids, context=context):
            new_fields = copy.deepcopy(all_field)
            [field.update(self.card_show_val(uid, record, field, context=context, user=user))
             for field in new_fields]
            return {'fieldVals': new_fields, 'id': record.id}
        if not record_ids:
            record = pool.get(model_name)
            for field in all_field:
                field.update({
                    'invisible': eval(field.get('invisible') or 'False'),
                    'readonly': eval(field.get('readonly') or 'False'),
                    'required': eval(field.get('required') or 'False'),
                })
        return {'fieldVals': all_field, 'id': 0}

    # /odoo/form/view/data
    @http.route('/odoo/mobile/form/view/data', auth='mobile', type='http', method=['GET'])
    def get_odoo_view_data(self, **args):
        """
        根据Grid搜索出来具体的视图配置信息
        :param args:
        :return:
        """
        cr, context, pool = request.cr, request.context, request.registry
        uid = request.session.get('uid') or SUPERUSER_ID
        model_name = args.get('model', '')
        view_id = int(args.get('viewId', '0'))
        id = int(args.get('id', '0'))
        view_row = pool.get('mobile.view').browse(cr, uid, view_id, context=context)
        return_val = {}
        if model_name:
            return_val = self.get_form_view_data(pool, cr, uid, view_row.show_form_view, id, model_name,
                                                 context=context)
        return simplejson.dumps(return_val)

    @http.route('/odoo/mobile/model/name_search', auth='mobile', type='http', method=['GET'])
    def get_odoo_model_name_search(self, **args):
        """
        search 方法 简单的调用odoo的search方法起到搜索的结果
        :param args:
        :return:
        """
        cr, context, pool = request.cr, request.context, request.registry
        uid = request.session.get('uid') or SUPERUSER_ID
        model_name = args.get('model')
        limit = int(args.get('limit', '15'))
        value = args.get('value', '')
        domain = eval(args.get('domain', '[]'))
        model_row = pool.get(model_name)
        return_val_list_dict = []
        if model_row:
            if value:
                return_val = getattr(model_row, 'name_search')(cr, uid, name=value, operator='ilike', args=domain,
                                                               limit=limit, context=context)
            else:
                return_ids = getattr(model_row, 'search')(cr, uid, domain, limit=limit, context=context)
                return_val = getattr(model_row, 'name_get')(cr, uid, return_ids, context=context)
            return_val_list_dict = [{'key': val[0], 'value': val[1]} for val in return_val]
        return simplejson.dumps(return_val_list_dict)

    def construct_model_vals(self, id, vals):
        """
        根据前端的返回值 构造拼接 需要写入数据的val
        :param id:
        :param vals:
        :return:
        """
        dict_val = {}
        for val in vals:
            if not val.get('value'):
                continue
            if val.get('type') in ('text', 'char', 'date', 'selection') \
                    and val.get('name') != 'id':
                dict_val.update({val.get('name'): val.get('value')})
            elif val.get('type') in ['datetime']:
                # TODO 这个8小时要换成可配置的，根据时区来判定。
                date_obj = datetime.datetime.strptime(val.get('value', 0) + ':00', ISODATETIMEFORMAT)
                dict_val.update({val.get('name'): (date_obj - relativedelta(hours=8)).strftime(ISODATETIMEFORMAT)})
            elif val.get('type') in ['integer', 'many2one']:
                dict_val.update({val.get('name'): int(val.get('value', 0))})
            elif val.get('type') in ['float']:
                dict_val.update({val.get('name'): float(val.get('value', 0))})
            elif val.get('type') in ['one2many']:
                line_vals = []
                line_ids, origin_ids = [], val.get('ids')
                for line_val in val.get('value'):
                    line_ids.append(line_val.get('id'))
                    record_row = {}
                    for field in line_val.get('meta'):
                        record_row.update({field.get('name'): field.get('value')})
                    if not id or not line_val.get('id'):
                        line_vals.append((0, 0, record_row))
                    else:
                        line_vals.append((1, line_val.get('id'), record_row))
                if origin_ids and origin_ids:
                    for delete_id in set(origin_ids) - set(line_ids):
                        line_vals.append((2, delete_id, False))
                dict_val.update({val.get('name'): line_vals})
            elif val.get('type') in ['many2many']:
                dict_val.update({val.get('name'): [(6, 0, val.get('value', []))]})
        return dict_val

    @http.route('/odoo/mobile/save/record', auth='mobile', type='json', method=['POST'])
    def create_new_record(self, **args):
        """
        新建修改都用这个方法，内部再进行处理
        :param args:
        :return:
        """
        cr, context, pool = request.cr, request.context, request.registry
        uid = request.session.get('uid') or SUPERUSER_ID
        model = request.jsonrequest.get('model')
        vals = request.jsonrequest.get('value')
        id = request.jsonrequest.get('id')
        vals = self.construct_model_vals(id, vals)
        context_val = eval(request.jsonrequest.get('context', '{}') or '{}')
        try:
            if not id:
                vals.update(context_val.get('default_vals', {}))
                if pool.get(model).create(cr, uid, vals, context=context):
                    return {'success': True, 'errMsg': u'创建成功！'}
                else:
                    return {'success': False, 'errMsg': u'创建失败！'}
            else:
                if pool.get(model).write(cr, uid, id, vals, context=context):
                    return {'success': True, 'errMsg': u'修改成功！'}
                else:
                    return {'success': False, 'errMsg': u'修改失败！'}
        except Exception as exc:
            # TODO odoo 返回的错误返回值不太固定，偶尔会有拦截不到的情况，还需进一步探索
            if isinstance(exc, basestring):
                return {'success': False, 'errMsg': u'%s' % exc}
            if exc and hasattr(exc, 'value'):
                return {'success': False, 'errMsg': u'%s' % exc.value}
            if exc and hasattr(exc, 'message') and hasattr(exc, 'diag'):
                return {'success': False, 'errMsg': u'%s' % exc.diag.message_primary}
            elif exc and hasattr(exc, 'message'):
                return {'success': False, 'errMsg': u'%s' % exc.message}

    @http.route('/odoo/mobile/login', auth='public', type='json', method=['POST'])
    def login_mobile(self, **kwargs):
        """
        简单的登录系统
        :param kwargs:
        :return:
        """
        # TODO 系统登录 这个还有点问题，当seesion过期，odoo会自动跳转到odoo的链接，AJAX请求无法捕获这个重定向 。
        name = request.jsonrequest.get('name')
        password = request.jsonrequest.get('password')
        ensure_db()
        uid = request.session.authenticate(request.httpsession.db, name, password)
        if not request.uid:
            request.uid = uid
            request.oauth_uid = uid
        if uid:
            return {'success': True, 'errMsg': u'登录成功！', 'uid': uid}
        else:
            error = "Wrong login/password"
            return {'success': False, 'errMsg': error}

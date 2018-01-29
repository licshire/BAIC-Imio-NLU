#coding=utf-8

import time

from common.CommonFunctions import *
from nlang.Constants import *
from db.CouchbaseAcc import *


def get_intention_id_map(intention):
    print('Connecting DB')
    with CouchbaseAcc(bucket=OBJ_CNFG_BUCKET, passwd=DEV_CFG_BUCK_PWD) as cb:
        print('DB Connection established')
        if intention.lower() == 'all':
            intent_map = cb.get(INTENT_ID_MAP_KEY)
        else:
            intent_map = cb.get_properties(INTENT_ID_MAP_KEY, intention)
    print(intent_map)
    return intent_map


def generate_ai_response(user_uuid, trxid, intention_id, speech, results=[], err_code='0', domain=''):
    rp_hdr = AI_RP_HEADER
    if user_uuid is None or trxid is None:
        intention_id = -10000
        domain = 'unknown'
        speech = 'Illegal AI request, lack of user ID or transaction ID'
    return {
        rp_hdr: {
            'trxid': trxid,
            'intention_id': intention_id,
            'domain': domain,
            'speech': speech,
            'results': results,
            'error_code': err_code,
            'cloud_time': str(time.time())
        }
    }


class IntentionID(object):
    INTENT_ID_MAP = None

    @classmethod
    def refresh(cls):
        cls.INTENT_ID_MAP = get_intention_id_map('all')

    @classmethod
    @property
    def map(cls):
        print('Am I in???')
        return cls.INTENT_ID_MAP

    @classmethod
    def getid(cls, intention):
        if cls.INTENT_ID_MAP is None:
            cls.refresh()
        intent_id = dict_get_value(cls.INTENT_ID_MAP, intention.lower(), -10000)
        print(intent_id)
        return intent_id


def add_entity_type(ent_type_name_en, ent_type_name_zh, entities={}):
    with CouchbaseAcc(bucket=OBJ_CNFG_BUCKET, passwd=DEV_CFG_BUCK_PWD) as cbc:
        prefix = 'ENT_T'
        init_table = False
        existing_types = cbc.get(ENTITY_TYPE_TABLE)
        if existing_types is None or len(existing_types) == 0:
            new_id_num = '1'
            init_table = True
        else:
            new_id_num = str(int(max(list(existing_types.keys())).lstrip(prefix)) + 1)
        new_type_id = prefix + new_id_num.zfill(5)
        type_value = {
            'en-US': ent_type_name_en,
            'zh-CN': ent_type_name_zh
        }
        #print(new_type_id)
        if init_table:
            cbc.add(ENTITY_TYPE_TABLE, {new_type_id: type_value})
        else:
            cbc.update(ENTITY_TYPE_TABLE, new_type_id, type_value)
        cbc.add(new_type_id, entities)
    return


def add_entity(entity_type, entity_normalize_val, entity_vals, lang='zh-CN'):
    with CouchbaseAcc(bucket=OBJ_CNFG_BUCKET, passwd=DEV_CFG_BUCK_PWD) as cbc:
        if entity_type.startswith('ENT_T'):
            entity_type_id = entity_type
        else:
            try:
                entity_type_id, entity = [
                    (k, v)
                    for k, v in cbc.get(ENTITY_TYPE_TABLE).items()
                    if v.get(lang) == entity_type
                ][0]
            except ValueError:
                return False, 'Specified entity type not exist yet, please add entity type first'
            except Exception as e:
                tb = sys.exc_info()[2]
                return False, '[Server Internal Error:] %s' % e.with_traceback(tb)
        val_path = '%s.%s' % (entity_normalize_val, lang)
        entity_vals.insert(0, True)
        updates = [(val_path, entity_vals, 'ad')]
        if lang != 'en-US':
            en_val_path = '%s.%s' % (entity_normalize_val, 'en-US')
            en_val = ' '.join([s.capitalize() for s in entity_normalize_val.split('-')])
            updates.append((en_val_path, [True, en_val], 'ad'))
        rs = cbc.update_multi(entity_type_id, updates)
        if not rs:
            msg = cbc.get_db_error()
        else:
            msg = 'Succeeded'
    return rs, msg


def add_entities(entities):
    with CouchbaseAcc(bucket=OBJ_CNFG_BUCKET, passwd=DEV_CFG_BUCK_PWD) as cbc:
        for e in entities:
            lang = e.get('lang')
            entity_type = e.get('type')
            entity_norm_val = e.get('normalized_value')
            entity_values = e.get('values')
    return


def init_types_db_docs():
    with CouchbaseAcc(bucket=OBJ_CNFG_BUCKET, passwd=DEV_CFG_BUCK_PWD) as cbc:
        types = list(cbc.get(ENTITY_TYPE_TABLE).keys())
        for t in types:
            cbc.add(t, {})


def load_zh_entities(sample_file):
    fp = open(sample_file, 'rt')
    examples = dict_get_value(json.load(fp), 'common_examples', None)
    with CouchbaseAcc(bucket=OBJ_CNFG_BUCKET, passwd=DEV_CFG_BUCK_PWD) as cbc:
        lamps = dict()
        rooms = dict()
        colors = dict()
        walls = dict()
        unknown = dict()
        #processed_entities = list()
        etypes = cbc.get(ENTITY_TYPE_TABLE)
        lamp_id = [k for k, v in etypes.items() if v.get('en-US')=='lamp'][0]
        room_id = [k for k, v in etypes.items() if v.get('en-US')=='room'][0]
        color_id = [k for k, v in etypes.items() if v.get('en-US')=='color'][0]
        wall_id = [k for k, v in etypes.items() if v.get('en-US')=='wall'][0]
        #print(lamp_id)
        #print(room_id)
        #print(color_id)
        #print(wall_id)

        for exmp in examples:
            entities = exmp.get('entities', [])
            if len(entities) == 0:
                continue
            for e in entities:
                values_cn = list()
                values_en = list()
                value = e.get('value', '')
                values_cn.append(value)
                entity = e.get('entity', '')
                values_en.append(' '.join([s.capitalize() for s in entity.split('-')]))
                entry = {
                    entity: {
                        'zh-CN': values_cn,
                        'en-US': values_en
                    }
                }
                if entity.find('lamp') != -1 or entity.find('light') != -1:
                    data = lamps
                    #print(data)
                elif entity.find('room') != -1 or entity == 'library' or entity == 'veranda':
                    data = rooms
                elif entity.find('white') != -1 or \
                        entity.find('red') != -1 or \
                        entity.find('yellow') != -1 or \
                        entity.find('green') != -1 or \
                        entity.find('blue') != -1 or \
                        entity.find('orange') != -1 or \
                        entity.find('purple') != -1:
                    data = colors
                elif entity.find('wall') != -1:
                    data = walls
                else:
                    data = rooms
                    #data = unknown
                if entity in list(data.keys()):
                    values = data.get(entity).get('zh-CN')
                    if value in values:
                        continue
                    else:
                        #print(values)
                        values_cn.extend(values)
                data.update(entry)
        #print('lamps: \n\t%s' % lamps)
        #print('rooms: \n\t%s' % rooms)
        #print('colors: \n\t%s' % colors)
        #print('walls: \n\t%s' % walls)
        #print('unknown: \n\t%s' % unknown)
        
        cbc.update(key=lamp_id, path=None, value=lamps)
        cbc.update(key=room_id, path=None, value=rooms)
        cbc.update(key=color_id, path=None, value=colors)
        cbc.update(key=wall_id, path=None, value=walls)
        cbc.update(key='ENT_UNKNOWN', path=None, value=unknown)


def main():
    #init_types_db_docs()
    add_entity('灯', 'atmosphere-lamp', ['氛围灯', '效果灯', '跑马灯'])
    """
    load_zh_entities(RASA_SAMPLES_FILE)

    add_entity_type('lamp', '灯')
    add_entity_type('room', '房间')
    add_entity_type('color', '颜色')
    add_entity_type('orientation', '方位')
    add_entity_type('direction', '方向')
    add_entity_type('state', '状态')
    add_entity_type('action', '动作')
    add_entity_type('wall', '墙')
    """


if __name__ == '__main__':
    main()

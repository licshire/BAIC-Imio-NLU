import json
import time

from rasa_nlu.config import *
from rasa_nlu.data_router import *

from ilogging.Logger import *
from nlang.TrioAIHelper import *
from nlang.Constants import *
from nlang.CommonFunctions import *
from nlang.MorAIHelper import *
from nlang.MsSpeechHelper import *
from mqprocessor.MqttProcessor import MqttProcessor
from couchbase.n1ql import N1QLQuery
from db.CouchbaseAcc import CouchbaseAcc
from db.Constants import *
from devices.DeviceHelper import *
from devices.constants import *
from users.UserManager import *
from marshaling.marshaling_device import *


class RasaAgent(object):
    """
    This is an AI agent mainly for processing NLU request via RASA_NLU framework.
    However, we still reserve the Moran route in it as well for contingency use.
    """
    def __init__(self, rasa_conf_file=DEFAULT_RASA_CONF_FILE):
        self.__rasa_config = RasaNLUConfig(rasa_conf_file, os.environ)
        self.__rasa_router = DataRouter(self.__rasa_config, None)
        self.__rasa_intention_map = self._load_rasa_intent_map()
        print(self.__rasa_intention_map)

    def _load_rasa_intent_map(self):
        fp = open(RASA_INTENTIONS_ID_MAP, 'rt')
        return json.load(fp)

    def get_intent_id(self, intention):
        return self.__rasa_intention_map.get(intention, -10000)

    def run_local_query(self, request):
        """
        Run the NLU query locally (Using RASA_NLU framework) by default, if the intention
        is not resolved, then forward it to Moran
        :param request: A dict object contains the query text, follows the format that RASA
                        DataRouter can extract, it must contains fields like below:
                        {
                            "user_id": "<UUID of the user who initiate the request>, required",
                            "trxid":
                            "q": "<speech text, required>",
                            "project": "<the name of the trained RASA project, optional>",
                            "model": "<the name of the trained model belongs to the RASA project, optional>"
                        }
                        Presently, we actually don't require the "project" and "model" field in the request,
                        we know exactly what projects and models the service needs from RASA we trained, so we
                        don't need to expose these information to users/clients to specify for resolving texts.
        :return: The response message in JSON format
        """
        user_uuid = request.pop('user_id', None)
        trxid = request.pop('trxid', None)
        speech = request.get('q', None)
        if user_uuid is None\
                or trxid is None\
                or speech is None:
            return None
        data = self.__rasa_router.extract(request)
        raw_response = self.__rasa_router.parse(data)
        print('raw_response:')
        print(raw_response)
        confidence = raw_response.get('intent', {}).get('confidence', '')
        print(confidence)
        if confidence < 0.8:
            response = generate_ai_response(user_uuid,
                                            trxid,
                                            IntentionID.getid('UNKNOWN'),
                                            speech,
                                            err_code=str(-1),
                                            domain='UNKNOWN')
            return response
        intention = raw_response.get('intent', {}).get('name', 'UNKNOWN')
        entities = raw_response.get('intent', {}).get('entities', 'UNKNOWN')
        intention_id = self.get_intent_id(intention)
        return raw_response


def run_query(user_uuid, trxid, text, init_channel=None, debug=False):
    """
    Entrance of all AI requests, the given text will be passed to AI Engine to parse to
    intentions and relevant parameters, and execute instructions if there is any per parsed results,
    or perform searching request, etc.
    :param user_uuid: The user ID of whom initiates the request.
    :param trxid: The transaction ID for labeling and recording the request.
    :param text: The text holds the request information that need to be parsed by AI engine.
    :return: A JSON format document contains the result of the request
    """
    if text.lower() == 'hi' \
         or text.lower() == 'hello' \
         or text == '你好':
        speech = '你好，我是妙琦，欢迎使用IMIO语音家居助手'
        response = generate_ai_response(user_uuid, trxid, IntentionID.getid('greetings'), speech)
        return response
    else:
        #print('AI Request from user %s:' % user_uuid)
        mor = MorAIAgent()
        # To parse the request, and output result is the parsed intention information
        parse_results = mor.parse_intention(query=text)
        #print('Parsed results:')
        #print(parse_results)
        intention = parse_results.get('intention')
        domain = parse_results.get('domain')
        speech = parse_results.get('speech')
        print('intention = %s' % intention)
        if intention == 'UNKNOWN':
            response = generate_ai_response(user_uuid, trxid, IntentionID.getid(intention), speech, err_code='-1')
        elif intention == 'instructing':
            commands = parse_results.get('commands', None)
            if commands is None or len(commands) == 0:
                # In this case, it is not a IMIO customized device controlling intention, it must be a
                # Moran built-in intention, and still it is an "instructing" intention.
                semantic = parse_results.get('semantic', {})
                instruction = semantic.get('instruction', ['UNKNOWN'])[0]
                values = semantic.get('value', [])
                #instruction_intention_dispatch(trxid, init_channel, instruction)
                intention_id = IntentionID.getid(instruction)
                response = generate_ai_response(user_uuid, trxid, intention_id, speech, values, err_code='0')
                print('final response:')
                print(response)
                return response
            for cmd in commands:
                cmd_intention = cmd.get('intention', 'UNKNOWN')
                cmd_domain = cmd.get('domain', 'UNKNOWN')
                cmd_params = cmd.get('params', [])
                cmd_params.update({'uid': user_uuid})
                intention = cmd_intention
                domain = cmd_domain
                exec_result = dict()
                instruction_intention_dispatch(trxid, init_channel, cmd_intention, cmd_domain, cmd_params, exec_result, debug)
                retcode = exec_result.get('code', 0)
                if retcode != 0:
                    speech = exec_result.get('msg', '')
                    #print('execution result message:')
                    #print(speech)
            response = generate_ai_response(user_uuid,
                                            trxid,
                                            IntentionID.getid(intention),
                                            speech,
                                            err_code=str(retcode),
                                            domain=domain)
        else:
            reply = parse_results.get('params', {})
            results, update_speech = general_intention_dispatch(intention, domain, reply)
            if update_speech:
                speech = ''
                for item in results:
                    speech += item
            response = generate_ai_response(user_uuid, trxid,
                                            IntentionID.getid(domain),
                                            speech,
                                            results=results,
                                            err_code='0',
                                            domain=domain)
        # Convert speech text to speech audio stream
        """
        results = response.get(AI_RP_HEADER).get('results')
        spch_helper = SpeechHelper(lang='zh-CN', gender='Male')
        #print('speech:')
        #print(speech)
        audio = spch_helper.text_to_speech(speech)
        aud_buff = b64encode(audio)
        results.append({'tts': aud_buff.decode('utf-8')})
        """
        print('final response:')
        print(response)
        return response


def general_intention_dispatch(intention, domain, reply):
    if intention == 'chatting' or intention == 'calculating'\
            or intention == 'greetings':
        return [], False
    elif intention == 'listening':
        results = list()
        contents = reply.get(list(reply.keys())[0], [])
        if domain == 'news':
            for c in contents:
                brief = c.get('abstracts', '')
                details = c.get('content', '')
                '''
                results.append({
                    'brief': brief,
                    'detail': details
                })
                '''
                results.append(brief)
        for c in contents:
            brief = c.get(list(c.keys())[0], '')
            results.append(brief)
        return results, False
    else:
        return reply.get(list(reply.keys())[0], []), False


def instruction_intention_dispatch(trxid, init_channel, intention, domain=None, params=None, exec_result={}, debug=False):
    """
    Dispatch the intention to specific executor after the request is successfully parsed. The input intention, parameters
    are the output of AI engine.
    :param trxid: The transaction ID of the request
    :param intention: The intention that is parsed from the request by AI enegine.
    :param params: The specific parameters that are parsed from the request.
    :param exec_result: The execute result contains detail message which may be used as response speech.
    :return: The exec_msg, or just nothing, this is reserved for possible future usage.
    """
    uid = params.pop('uid')
    if intention == 'bind_sub':
        perform_gw_action(intention, init_channel, trxid, debug)
        return
    elif intention == 'light-control':
        if not light_control(trxid, domain, uid, params, debug):
            exec_result.update({
                'code': -1,
                'msg': 'There is no operable device online'
            })
        return
    elif intention == 'curtain-control':
        if not curtain_control(trxid, uid, params, debug):
            exec_result.update({
                'code': -1,
                'msg': 'The curtain(s) you are asking to control is not online'
            })
        return
    else:
        exec_result.update({
            'code': -100,
            'msg': 'Unrecognized instruction'
        })
        return


def perform_gw_action(action_name, gw_channel, trxid, debug=False):
    back_channel = 'IN@' + gw_channel
    req = build_device_action_req(action_name, trxid)
    MqttProcessor.single_publish(topic=back_channel, message=json.dumps(req))


def light_control(trxid, domain, user_uuid, params, debug=False):
    rv = False
    user_profile = get_user_info_by_ext_uuid(user_uuid, 'ext_uuid', 'uuid', 'houses', 'cell_no', 'access_token', 'lang')
    if user_profile is None or len(user_profile) == 0:
        LOG_INFO(os.getenv('NODE_ID'), 'JBS', os.getpid(), '[DEBUG][AI Failure] User is not even found???')
        return False
    user = UserProfile(user_profile)
    user_dev_list = user.online_devices('10001', '10002', '10003', '10010-01', '10020-01')
    if user_dev_list is None or len(user_dev_list) == 0:
        user_dev_list = user.owned_devices('10001', '10002', '10003', '10010-01', '10020-01')
        if user_dev_list is None or len(user_dev_list) == 0:
            LOG_INFO(os.getenv('NODE_ID'), 'JBS', os.getpid(), '[DEBUG][AI Failure] None of my devices is not even found???')
            return False
    tgt_room_name = params.get('room_name_val', 'NULL')
    tgt_lamp_name = params.get('lamp_name_val', 'lamp')
    tgt_sts = params.get('status_val', 'on')
    tgt_bri = params.get('brightness_val', 'default')
    tgt_color = params.get('color_value', 'default')
    if tgt_sts == 'off':
        switch = 0
    else:
        switch = 1

    target_args = {
        'switch': switch,
        'brightness': tgt_bri,
        'color': tgt_color
    }

    for dev in user_dev_list:
        dev_type = dev.get('type', '10001')
        room_name = dev.get('room_id', 'NULL').split('.')[-1]
        if tgt_room_name is not None and 0 != len(tgt_room_name):
            if room_name != tgt_room_name:
                continue

        if dev_type == '10010-01' or dev_type == '10020-01':
            sub_devices = dev.get('sub_devices', None)
            if sub_devices is None:
                continue
        gw_uuid = dev.get('uuid', None)
        if gw_uuid is None:
            continue
        rv = post_led_actions(trxid, domain, dev, tgt_lamp_name, target_args, debug)
    return rv


def post_led_actions(trxid, domain, dev, tgt_lamp_name, target_args, debug=False):
    sub_actions = list()

    # parse target status values from given args
    switch = target_args.get('switch')
    bri_dir = target_args.get('brightness')
    color = target_args.get('color')
    rgb_val = parse_led_color_values(color)

    channel_no = dev.get('channel_no', None)
    if channel_no is None or 'NULL' == channel_no:
        # if the device is not online, directly return
        LOG_INFO(os.getenv('NODE_ID'), 'JBS', os.getpid(), '[DEBUG] GW is not even online???')
        return False
    sub_devices = dev.get('sub_devices', {})
    LOG_INFO(os.getenv('NODE_ID'), 'JBS', os.getpid(), '[DEBUG] AI All Found Devices:\n\t%s' % sub_devices)
    for dev_id in sub_devices:
        device = sub_devices.get(dev_id)
        #print('SUB-DEV:')
        #print(device)
        dev_type = device.get('type')
        if dev_type == '10010-01-22001' \
                or dev_type == '10010-01-09001' \
                or dev_type == '10010-01-25001' \
                or dev_type == '10010-01-26001':
            if domain == 'light-brightness':
                if dev_type == '10010-01-09001' or dev_type == '10010-01-22001':
                    continue
            if domain == 'light-color' and dev_type != '10010-01-25001':
                continue
            switch_type = device.get('switch_type', 1)
            stats = device.get('sta', [{'bri': device.get('bri', LED_MIN_BRI)}])
            for ep in range(switch_type):
                curr_bri = stats[ep].get('bri', LED_MIN_BRI)
                bri_val = parse_brightness(bri_dir, curr_bri)
                action = build_led_ops_params(dev_id, dev_type, ep+1, switch, bri_val, rgb_val.value)
                sub_actions.append(action)
    if len(sub_actions) != 0:
        action_req = build_device_action_req('sub_actions', trxid, sub_actions)
        if channel_no is not None and 'NULL' != channel_no:
            MqttProcessor.single_publish(topic='IN@' + channel_no, message=json.dumps(action_req))
            if debug:
                LOG_INFO(os.getenv('NODE_ID'), 'JBS', os.getpid(),
                         '[DEBUG] AI Device Control Request:\n\t%s' % action_req)
            return True
        else:
            #print('No lighting device is online')
            return False
    else:
        return False


def curtain_control(trxid, user_uuid, params, debug=False):
    no_curtain_msg = 'Can\'t find any curtain in your online device list'
    user_profile = get_user_info_by_ext_uuid(user_uuid, 'ext_uuid', 'uuid', 'houses', 'cell_no', 'access_token', 'lang')
    if user_profile is None or len(user_profile) == 0:
        return False
    user = UserProfile(user_profile)
    devices = user.owned_devices('10010-01', '10020-01')
    if devices is None or len(devices) == 0:
        return False
    tgt_room_name = params.get('room_name_val', 'NULL')
    switch = parse_direction(params.get('action', 'open'))

    found_dev = False
    for dev in devices:
        room_name = dev.get('room_id', 'NULL').split('.')[-1]
        if tgt_room_name is not None and 0 != len(tgt_room_name):
            if room_name != tgt_room_name:
                continue
        sub_devices = dev.get('sub_devices', None)
        if sub_devices is None or len(sub_devices) == 0:
            continue

        sub_actions = list()
        channel_no = dev.get('channel_no', None)
        if channel_no is None or 'NULL' == channel_no:
            continue
        for dev_id in sub_devices:
            device = sub_devices.get(dev_id)
            dev_type = device.get('type')
            if dev_type == '10010-01-51001':
                found_dev = True
                action = {
                    'type': dev_type,
                    'dev_id': dev_id,
                    'ep': 8,
                    'sw': switch
                }
                sub_actions.append(action)
        action_req = {
            'subdevice_action_req': {
                'sub_actions': sub_actions,
                'cloud_time': str(time.time()),
                'trxid': trxid
            }
        }
        if found_dev:
            MqttProcessor.single_publish(topic='IN@' + channel_no, message=json.dumps(action_req))
    if found_dev:
        return True
    else:
        return False


def main():
    request = {
        'q': '把灯打开',
        'user_id': 'dd9c26e3e5f5548ea530222ba197cac356b3c332cc08ce178c0d8eb98733c714',
        'trxid': 'AI-1234567890'
    }
    """
    response = run_query('dd9c26e3e5f5548ea530222ba197cac356b3c332cc08ce178c0d8eb98733c714',
              'AI-1234567890',
              '把音量调小')
    print(response)
    """
    #request = {'q': '你好'}
    #config_file = './conf/rasa_config_zh.json'
    #rasa_config = RasaNLUConfig(config_file, os.environ)
    #router = DataRouter(rasa_config, None)
    #req_data = router.extract(request)
    #response = router.parse(req_data)
    #print(response)
    ra = RasaAgent()
    response = ra.run_local_query(request)
    print('response:')
    print(response)


if __name__ == '__main__':
    main()

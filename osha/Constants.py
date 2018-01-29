import time
from enum import Enum
from db.CouchbaseAcc import *
from common.CommonFunctions import *


__all__ = ['MS_APP_ID', 'MS_APP_PWD', 'MS_COG_HOST', 'MS_COG_STT_TTS_KEY', 'INTENT_ID_MAP_KEY', 'Commands',
           'LedColorValues', 'AI_RP_HEADER', 'UNKNOWN_INT', 'DEFAULT_RASA_CONF_FILE', 'RASA_INTENTIONS_ID_MAP',
           'RASA_SAMPLES_FILE', 'ENTITY_TYPE_TABLE'
          ]


UNKNOWN_INT = -10000
INTENT_ID_MAP_KEY = 'intention_id_map'
ENTITY_TYPE_TABLE = 'nlu_entity_types'


# RASA configuration constants
DEFAULT_RASA_CONF_FILE = os.path.join(CLOUD_HOME, 'nlang/conf/rasa_config_zh.json')
RASA_INTENTIONS_ID_MAP = os.path.join(CLOUD_HOME, 'nlang/conf/rasa_intention_id_map.json')
RASA_SAMPLES_FILE = os.path.join(CLOUD_HOME, 'nlang/data/imio_lc_zh.json')


# Microsoft STT service related constants
MS_APP_ID = '950f8ca2-1b6e-41b3-a90c-c7775997603e'
MS_APP_PWD = 'EWwjGB3hU47BfrqcGfYEKfC'
MS_COG_HOST = 'westus.api.cognitive.microsoft.com'
MS_COG_STT_TTS_KEY = 'ac594ac6e4474f5a9c2a0c9fefff697b'
MS_COG_STT_TTS_KEY2 = '20710bb7f30f4fffaf3124b28a94f57f'


# Protocol of cloud and device interactions constants
AI_RP_HEADER = 'device_ai_rep'


class Commands(Enum):
    CHATTING = 1000
    STOP = 1001
    LIGHT_ON = 1002
    LIGHT_OFF = 1003
    CURTAIN_OPEN = 1004
    CURTAIN_CLOSE = 1005
    CURTAIN_STOP = 1006
    UNKNOWN = -1001


class LedColorValues(Enum):
    """
    Date: Nov 16th, 2017
    This is specific for the LED light controller we are using now,
    the supplier uses 3 parameters, "hue", "saturation", "temperature"
    to present a specific color. So the value uses 3 dimension duple,
    the 1st position represent hue, 2nd for saturation, 3rd for temperature.
    However int the future, this also will be able to represent RGB colors.
    """
    WHITE = (0, 0, 499)
    RED = (254, 200, 499)
    GREEN = (100, 254, 499)
    BLUE = (182, 200, 499)

# src/parameters.py

# 本类中存储了所有动画的路径
class ANIMATION_PATH:
    # ======== 默认状态与移动 ========
    # 默认状态
    BASIC_CONT_RIGHT = ['assets/images/basic_right_0.png']
    BASIC_CONT_LEFT = ['assets/images/basic_left_0.png']

    # 移动
    MOVEMENT_CONT_LEFT = ['assets/images/movement_walk_left_0.png']
    MOVEMENT_CONT_RIGHT = ['assets/images/movement_walk_right_0.png']

    # 拖拽与拖拽结束
    MOVEMENT_CONT_DRAG = ['assets/images/movement_drag_0.png']

    # 拖拽结束后的掉落与站起
    MOVEMENT_CONT_FALL = ['assets/images/movement_fall_0.png']
    MOVEMENT_SING_LAND = ['assets/images/movement_land_0.png']
    MOVEMENT_SING_STAND = ['assets/images/movement_stand_0.png']

    # ======== 用户互动行为 ========
    ACTION_SING_EAT = ['assets/images/action_eat_0.png']
    ACTION_SING_DRINK = ['assets/images/action_drink_0.png']
    ACTION_CONT_SLEEP = ['assets/images/action_sleep_0.png']
    ACTION_CONT_PLAY = ['assets/images/action_play_0.png']
    ACTION_CONT_CODE = ['assets/images/action_code_0.png']
    ACTION_CONT_STUDY = ['assets/images/action_study_0.png']
    ACTION_CONT_WORK = ['assets/images/action_work_0.png']
    ACTION_CONT_TEACH = ['assets/images/action_teach_0.png']
    ACTION_CONT_TALK = ['assets/images/action_talk_0.png']

    # ======== 情绪状态 ========
    EMOTION_SING_ANGRY = ['assets/images/emotion_angry_0.png']
    EMOTION_SING_HAPPY = ['assets/images/emotion_happy_0.png']
    EMOTION_SING_SAD = ['assets/images/emotion_sad_0.png']
    EMOTION_SING_ENJOY = ['assets/images/emotion_enjoy_0.png']
    EMOTION_SING_DISGUST = ['assets/images/emotion_disgust_0.png']
    EMOTION_SING_BLUSH = ['assets/images/emotion_blush_0.png']
    EMOTION_SING_SORRY = ['assets/images/emotion_sorry_0.png']

    # 可以添加其他的动画

class ANIMATION_CONFIG:
    # 各种动画的设置

    # 眨眼之类的静态行为
    CONFIG_BASIC_CONT = {"loop": True, "fps": 0.1}

    # 移动相关的动画
    CONFIG_MOVEMENT_CONT = {"loop": True, "fps": 5.0}
    CONFIG_MOVEMENT_SING = {"duration": 1,"loop": False, "fps": 5.0}
    
    # 用户互动行为
    CONFIG_ACTION_CONT = {"loop": True, "fps": 5.0}
    CONFIG_ACTION_SING = {"duration": 3, "loop": False, "fps": 5.0}

    # 情绪状态
    CONFIG_EMOTION_SING = {"duration": 5, "loop": False, "fps": 5.0}

API_KEY = ""
BASE_URL = ""
MODEL_NAME = ""
CODER_MODEL_NAME = ""
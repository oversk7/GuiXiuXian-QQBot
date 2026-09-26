"""可由命令边界识别的业务异常；此处不发送消息、不管理事务。"""


class InventoryCapacityError(ValueError):
    """物品入包需要的格数超过容量。

    保留 ValueError 继承关系和原错误文本，兼容已有的专属提示、保存点
    回滚及溢出处理。未被业务层处理时，应穿过事务边界后统一回复。
    """

    def __init__(self):
        super().__init__("背包空间不足")

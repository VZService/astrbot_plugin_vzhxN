from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.message_components import Plain
import random
import time
import asyncio
import platform
from typing import Dict, Any, Optional, List

PLUGIN_VERSION = "v1.2.7"

# 内置默认配置
DEFAULT_JRRP_COMMENTS = {
    "大吉": [
        "运气爆棚！今天的你如同被幸运女神亲吻，出门捡钱、抽卡必出货，快去试试手气吧！😄",
        "鸿运当头，万事如意！今天做什么都会顺利，连平时难搞的事情也会迎刃而解。",
        "天选之人就是你！今日运势极佳，不妨去买张彩票，说不定会有意外惊喜。"
    ],
    "吉": [
        "还不错哦！今天小确幸不断，保持好心情，会有好事发生。🙂",
        "运势良好，适合推进重要计划，与人交流会更顺畅。",
        "平稳中有上升，今天可以适当尝试新事物，会有收获。"
    ],
    "中吉": [
        "平平淡淡才是真，今天没有大风大浪，适合静心处理琐事。",
        "运势平稳，按部就班就好，注意细节避免小失误。",
        "今天适合学习和积累，为未来做准备。"
    ],
    "末吉": [
        "需要努力！今天可能会遇到一些挑战，但只要坚持就能克服。",
        "运势稍弱，但事在人为，多一份努力就多一份收获。",
        "适合反思和规划，不要急于求成。"
    ],
    "凶": [
        "运气不佳😢，今天可能会有点水逆，重要决定可以往后放一放。",
        "乌云盖顶，诸事不宜？别担心，今天宅家休息也是一种选择。",
        "运势走低，但也是积攒人品的时候，保持低调，明天会更好。"
    ]
}

DEFAULT_JRRP_EXTRAS = [
    "今天会有好事发生吗？保持期待～",
    "保持积极心态，好运自然来！",
    "或许可以试试新事物，比如学做一道菜。",
    "注意身体健康哦，多喝水，早点睡。",
    "适合休息一天，放松一下。",
    "与人分享快乐，快乐加倍！",
    "今天宜：整理房间，忌：熬夜。"
]

# 类型定义
class GuessGame:
    def __init__(self, target: int, min_val: int, max_val: int):
        self.target = target
        self.guesses = 0
        self.active = True
        self.min = min_val
        self.max = max_val

# 全局存储
guess_games: Dict[str, GuessGame] = {}          # 猜数字游戏状态，键为 unified_msg_origin
screen_tasks: Dict[str, asyncio.Task] = {}      # 刷屏任务，键为 group_id 字符串

@register("vz", "VZ", "VZ 核心插件", "1.0.0")
class ASbVZPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._running = True
        logger.info("核心已注入成功")

    # 辅助方法
    def _safe_get_list(self, key: str, default: List) -> List:
        """安全获取列表配置，若不是列表则返回默认值"""
        try:
            val = self.config.get(key, default)
            if isinstance(val, list):
                return val
            else:
                return default
        except Exception:
            return default

    def _safe_get_dict(self, key: str, default: Dict) -> Dict:
        """安全获取字典配置"""
        try:
            val = self.config.get(key, default)
            if isinstance(val, dict):
                return val
            else:
                return default
        except Exception:
            return default

    def _safe_get_bool(self, key: str, default: bool = True) -> bool:
        """安全获取布尔配置，兼容字符串与数字"""
        try:
            val = self.config.get(key, default)
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(val)
            if isinstance(val, str):
                value = val.strip().lower()
                if value in {"true", "1", "yes", "on", "enabled", "enable"}:
                    return True
                if value in {"false", "0", "no", "off", "disabled", "disable"}:
                    return False
            return bool(val)
        except Exception:
            return default

    # 功能指令
    @filter.command("about")
    @filter.command("关于")
    async def about(self, event: AstrMessageEvent):
        yield event.plain_result(
            f"==关于vzhx插件==\n"
            f"由 VZService 所有 vzservice.top\n"
            f"Github：VZService/astrbot_plugin_vzhx\n"
            f"版本：{PLUGIN_VERSION}\n"
            f"==============="
        )

    @filter.command("jrrp")
    async def jrrp(self, event: AstrMessageEvent):
        """今日运势"""
        if not self._is_enabled("enable_jrrp"):
            return

        luck_value = random.randint(1, 100)
        thresholds = self._safe_get_dict("jrrp_thresholds", {"大吉": 90, "吉": 70, "中吉": 50, "末吉": 30, "凶": 0})

        # 按阈值降序排序，确保最大阈值优先
        sorted_thresholds = sorted(thresholds.items(), key=lambda x: x[1], reverse=True)
        level = "凶"  # 默认
        for lvl, th in sorted_thresholds:
            if luck_value >= th:
                level = lvl
                break
        # 若仍未匹配（如阈值全为负），强制为凶
        if level not in thresholds:
            level = "凶"

        comments = self._safe_get_dict("jrrp_comments", {})
        level_comments = comments.get(level)
        if not level_comments or not isinstance(level_comments, list):
            level_comments = DEFAULT_JRRP_COMMENTS.get(level, ["运势未知"])
        comment = random.choice(level_comments)

        extras = self._safe_get_list("jrrp_extras", [])
        if not extras:
            extras = DEFAULT_JRRP_EXTRAS
        extra = random.choice(extras)

        reply = f"今日运势：{level}（人品值 {luck_value}）\n{comment}\n{extra}"
        yield event.plain_result(reply)

    @filter.command("投骰子")
    async def roll_dice(self, event: AstrMessageEvent):
        if not self._is_enabled("enable_dice"):
            return
        faces = self.config.get("dice_faces", 6)
        if not isinstance(faces, int) or faces < 2:
            faces = 6
        result = random.randint(1, faces)
        yield event.plain_result(f"🎲 掷出 {faces} 面骰子：{result}")

    @filter.command("冷知识")
    async def cold_knowledge(self, event: AstrMessageEvent):
        if not self._is_enabled("enable_cold_knowledge"):
            return
        facts = self._safe_get_list("cold_knowledge_list", [])
        if not facts:
            yield event.plain_result("🧊 冷知识库为空")
            return
        fact = random.choice(facts)
        yield event.plain_result(f"🧊 冷知识：{fact}")

    @filter.command("猜数字")
    async def guess_number(self, event: AstrMessageEvent, guess: str = None):
        if not self._is_enabled("enable_guess_number"):
            return

        user_key = event.unified_msg_origin
        range_cfg = self._safe_get_dict("guess_number_range", {"min": 1, "max": 100})
        min_val = range_cfg.get("min", 1)
        max_val = range_cfg.get("max", 100)

        # 无参数 -> 开始新游戏
        if guess is None:
            target = random.randint(min_val, max_val)
            guess_games[user_key] = GuessGame(target, min_val, max_val)
            yield event.plain_result(
                f"🎯 猜数字游戏开始！我想好了一个{min_val}-{max_val}之间的数字，"
                f"请用 猜数字 [数字] 来猜。"
            )
            return

        # 有参数 -> 尝试猜测
        try:
            guessed = int(guess)
        except ValueError:
            yield event.plain_result("请输入有效的数字！")
            return

        game = guess_games.get(user_key)
        if not game or not game.active:
            yield event.plain_result("你还没有开始游戏，请先发送 猜数字 开始新游戏。")
            return

        if guessed < game.min or guessed > game.max:
            yield event.plain_result(f"数字必须在{game.min}-{game.max}之间哦！")
            return

        game.guesses += 1

        if guessed < game.target:
            reply = f"📉 猜小了，再试试！（第{game.guesses}次猜测）"
        elif guessed > game.target:
            reply = f"📈 猜大了，再试试！（第{game.guesses}次猜测）"
        else:
            reply = f"🎉 恭喜猜中！数字就是 {game.target}，你用了 {game.guesses} 次猜对！游戏结束。"
            game.active = False

        yield event.plain_result(reply)

    @filter.command("废话")
    async def bullshit(self, event: AstrMessageEvent):
        if not self._is_enabled("enable_bullshit"):
            return
        bullshit_list = self._safe_get_list("bullshit_list", [])
        if not bullshit_list:
            yield event.plain_result("💬 废话库为空，请联系管理员")
            return
        line = random.choice(bullshit_list)
        yield event.plain_result(f"💬 {line}")

    @filter.command("营销号")
    async def yingxiao(self, event: AstrMessageEvent, topic: str = ""):
        if not self._is_enabled("enable_yingxiao"):
            return
        if not topic:
            topic = random.choice([
                "睡觉时手机放床头", "喝奶茶", "熬夜", "吃泡面",
                "养猫", "刷短视频", "单身", "加班"
            ])

        titles = self._safe_get_list("yingxiao_titles", [])
        bodies = self._safe_get_list("yingxiao_bodies", [])
        extras = self._safe_get_list("yingxiao_extras", [])

        if not titles or not bodies:
            yield event.plain_result("营销号模板缺失")
            return

        title = random.choice(titles).format(topic)
        body = random.choice(bodies).format(topic)
        extra = random.choice(extras) if extras else ""

        yield event.plain_result(f"📢 {title}\n\n{body}\n\n{extra}")

    @filter.command("刷屏")
    async def screen(self, event: AstrMessageEvent):
        """刷屏指令（仅管理员）"""
        if not self._is_enabled("enable_screen"):
            yield event.plain_result("刷屏功能已被禁用。")
            return

        if not event.is_admin():
            yield event.plain_result("❌ 权限不足：只有机器人管理员可以使用此指令。")
            return

        # 手动解析参数：刷屏 "文本" [次数] [毫秒]
        full_text = event.message_str.strip()
        parts = full_text.split()
        if len(parts) < 2:
            yield event.plain_result("用法：刷屏 \"文本\" [次数] [毫秒]\n示例：刷屏 \"你好啊\" 10 1000")
            return

        # 尝试提取带引号的文本
        raw = full_text[len(parts[0]):].strip()
        if raw.startswith('"') or raw.startswith("'"):
            quote = raw[0]
            end = raw.find(quote, 1)
            if end == -1:
                yield event.plain_result("未闭合的引号")
                return
            text = raw[1:end]
            rest = raw[end+1:].strip()
        else:
            yield event.plain_result("请使用引号包裹文本，例如：刷屏 \"你好\" 10 1000")
            return

        if not text:
            yield event.plain_result("文本内容不能为空。")
            return

        # 解析次数和间隔
        times = 10
        interval_ms = 999
        if rest:
            tokens = rest.split()
            try:
                times = int(tokens[0])
            except (ValueError, IndexError):
                pass
            if len(tokens) >= 2:
                try:
                    interval_ms = int(tokens[1])
                except ValueError:
                    pass

        if times == 0:
            times_desc = "无限"
        else:
            times_desc = str(times)
        interval_sec = interval_ms / 1000.0

        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("此指令只能在群聊中使用。")
            return
        group_id_str = str(group_id)

        # 取消已有任务
        if group_id_str in screen_tasks and not screen_tasks[group_id_str].done():
            screen_tasks[group_id_str].cancel()
            try:
                await screen_tasks[group_id_str]
            except asyncio.CancelledError:
                pass
            screen_tasks.pop(group_id_str, None)

        # 启动新任务
        umo = event.unified_msg_origin
        task = asyncio.create_task(self._do_screen(group_id_str, umo, text, times, interval_sec))
        screen_tasks[group_id_str] = task
        yield event.plain_result(
            f"✅ 刷屏任务已启动：\n"
            f"文本：{text}\n"
            f"次数：{times_desc}\n"
            f"间隔：{interval_ms} 毫秒"
        )

    async def _do_screen(self, group_id: str, umo: str, text: str, times: int, interval: float):
        """执行刷屏任务"""
        try:
            if times == 0:
                count = 0
                while self._running:
                    # 检查任务是否被取消
                    if asyncio.current_task().cancelled():
                        break
                    try:
                        chain = MessageChain().message(text)
                        await self.context.send_message(umo, chain)
                        count += 1
                        logger.info(f"刷屏任务：群{group_id} 已发送 {count} 次")
                        await asyncio.sleep(interval)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"刷屏发送失败: {e}")
                        break
            else:
                for i in range(times):
                    if not self._running or asyncio.current_task().cancelled():
                        break
                    try:
                        chain = MessageChain().message(text)
                        await self.context.send_message(umo, chain)
                        logger.info(f"刷屏任务：群{group_id} 发送第{i+1}/{times}次")
                        await asyncio.sleep(interval)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"刷屏发送失败: {e}")
                        break
        except asyncio.CancelledError:
            pass
        finally:
            if group_id in screen_tasks and screen_tasks[group_id] == asyncio.current_task():
                screen_tasks.pop(group_id, None)
            logger.info(f"刷屏任务：群{group_id} 结束")

    # 工具方法
    def _is_enabled(self, config_key: str) -> bool:
        return self._safe_get_bool(config_key, True)

    # 插件卸载
    async def terminate(self):
        self._running = False
        for task in screen_tasks.values():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        screen_tasks.clear()
        logger.info("核心已取消注入")

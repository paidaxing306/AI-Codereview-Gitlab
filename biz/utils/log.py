import logging
import os
import threading
from logging.handlers import RotatingFileHandler

# 自定义 Logger 类，重写 warn 和 error 方法
class CustomLogger(logging.Logger):
    def warn(self, msg, *args, **kwargs):
        # 在 warn 消息前添加 ⚠️
        msg_with_emoji = f"⚠️ {msg}"
        super().warning(msg_with_emoji, *args, **kwargs)  # 注意：warn 是 warning 的别名

    def error(self, msg, *args, **kwargs):
        # 在 error 消息前添加 ❌
        msg_with_emoji = f"❌ {msg}"
        super().error(msg_with_emoji, *args, **kwargs)


def get_log_file_name():
    """获取日志文件名，为每个进程创建独立的日志文件"""
    base_log_file = os.environ.get("LOG_FILE", "log/app.log")
    
    # 检查是否启用进程安全日志
    use_process_safe_logging = os.environ.get("USE_PROCESS_SAFE_LOGGING", "1") == "1"
    
    if use_process_safe_logging:
        # 获取进程ID和线程ID
        process_id = os.getpid()
        thread_id = threading.get_ident()
        
        # 分离文件名和扩展名
        base_name, ext = os.path.splitext(base_log_file)
        
        # 创建包含进程ID和线程ID的日志文件名
        log_file = f"{base_name}_pid{process_id}_tid{thread_id}{ext}"
    else:
        log_file = base_log_file
    
    return log_file


# 检查是否禁用文件日志
disable_file_logging = os.environ.get("DISABLE_FILE_LOGGING", "0") == "1"

log_file = get_log_file_name()
log_max_bytes = int(os.environ.get("LOG_MAX_BYTES", 10 * 1024 * 1024))  # 默认10MB
log_backup_count = int(os.environ.get("LOG_BACKUP_COUNT", 5))  # 默认保留5个备份文件
# 设置日志级别
log_level = os.environ.get("LOG_LEVEL", "INFO")
LOG_LEVEL = getattr(logging, log_level.upper(), logging.INFO)

# 使用自定义的 Logger 类
logger = CustomLogger(__name__)
logger.setLevel(LOG_LEVEL)  # 设置 Logger 的日志级别

# 添加控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(funcName)s:%(lineno)d - %(message)s'))
console_handler.setLevel(LOG_LEVEL)
logger.addHandler(console_handler)

# 只有在不禁用文件日志时才添加文件处理器
if not disable_file_logging:
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_file,
        mode='a',
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding='utf-8',
        delay=False
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(funcName)s:%(lineno)d - %(message)s'))
    file_handler.setLevel(LOG_LEVEL)
    logger.addHandler(file_handler)

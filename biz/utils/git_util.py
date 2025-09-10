import os
import subprocess
import shutil
from typing import Optional, Tuple
from urllib.parse import urlparse
from biz.utils.log import logger


class GitUtil:
    """
    Git操作工具类
    """
    
    @staticmethod
    def get_project_name_from_url(git_url: str) -> str:
        """
        从git URL中提取项目名称
        
        Args:
            git_url: git仓库URL
            
        Returns:
            项目名称
        """
        # 移除.git后缀
        if git_url.endswith('.git'):
            git_url = git_url[:-4]
        
        # 解析URL
        parsed = urlparse(git_url)
        path = parsed.path.strip('/')
        
        # 提取项目名称（最后一部分）
        project_name = path.split('/')[-1]
        
        return project_name
    
    @staticmethod
    def is_git_repository(path: str) -> bool:
        """
        检查指定路径是否为git仓库
        
        Args:
            path: 路径
            
        Returns:
            是否为git仓库
        """
        git_dir = os.path.join(path, '.git')
        return os.path.exists(git_dir) and os.path.isdir(git_dir)
    
    @staticmethod
    def clone_repository(git_url: str, target_path: str, token: Optional[str] = None) -> Tuple[bool, str]:
        """
        克隆git仓库
        
        Args:
            git_url: git仓库URL
            target_path: 目标路径
            token: 访问令牌（可选）
            
        Returns:
            (是否成功, 错误信息)
        """
        try:
            # 如果目标路径已存在，先删除
            if os.path.exists(target_path):
                logger.info(f"目标路径 {target_path} 已存在，正在删除...")
                shutil.rmtree(target_path)
            
            # 确保父目录存在
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            # 构建克隆命令
            git_url_to_use = git_url
            
            if token:
                # 如果提供了token，将其添加到URL中
                parsed_url = urlparse(git_url)
                if parsed_url.scheme in ['http', 'https']:
                    # HTTP/HTTPS URL，使用 //{token}:{token}@ 格式
                    netloc = parsed_url.netloc
                    if '@' in netloc:
                        # 如果URL中已经有用户名，替换用户名部分
                        host_part = netloc.split('@')[-1]
                        git_url_to_use = f"{parsed_url.scheme}://{token}:{token}@{host_part}{parsed_url.path}"
                    else:
                        git_url_to_use = f"{parsed_url.scheme}://{token}:{token}@{netloc}{parsed_url.path}"
                # 对于SSH URL，我们保持原样，因为token通常不适用于SSH
            
            # 执行克隆命令
            logger.info(f"正在克隆仓库: {git_url} 到 {target_path}")
            
            # 对于SSH URL，我们可能需要设置一些环境变量
            env = os.environ.copy()
            if git_url.startswith('ssh://'):
                # 对于SSH URL，确保SSH配置正确
                env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=no'
            
            # 在Windows上启用长路径支持
            if os.name == 'nt':  # Windows系统
                # 配置Git支持长路径
                subprocess.run(
                    ['git', 'config', '--global', 'core.longpaths', 'true'],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=30
                )
                # 配置Git使用Windows长路径API
                subprocess.run(
                    ['git', 'config', '--global', 'core.protectNTFS', 'false'],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=30
                )
            
            # 打印克隆命令
            clone_cmd = f"git clone {git_url_to_use} {target_path}"
            logger.info(f"执行git命令: {clone_cmd}")
            result = subprocess.run(
                ['git', 'clone', git_url_to_use, target_path],
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                env=env
            )
            
            if result.returncode == 0:
                logger.info(f"仓库克隆成功: {target_path}")
                return True, ""
            else:
                error_msg = f"克隆失败: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "克隆操作超时"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"克隆过程中发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def checkout_branch(repo_path: str, branch_name: str) -> Tuple[bool, str]:
        """
        切换到指定分支（兼容性方法，建议使用 ensure_repository）
        
        Args:
            repo_path: 仓库路径
            branch_name: 分支名称
            
        Returns:
            (是否成功, 错误信息)
        """
        try:
            if not GitUtil.is_git_repository(repo_path):
                return False, f"路径 {repo_path} 不是有效的git仓库"
            
            # 切换到指定分支
            logger.info(f"正在切换到分支: {branch_name}")
            logger.info(f"执行git命令: git checkout {branch_name}")
            result = subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"成功切换到分支: {branch_name}")
                return True, ""
            else:
                error_msg = f"切换分支失败: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "切换分支操作超时"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"切换分支过程中发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def ensure_repository(git_url: str, workspace_path: str, branch_name: str = "master", token: Optional[str] = None) -> Tuple[bool, str]:
        """
        智能确保仓库存在并更新到最新代码
        
        逻辑：
        1. 如果项目不存在 -> 克隆项目 -> 切换到指定分支
        2. 如果项目已存在 -> 切换到指定分支 -> git pull 拉取最新代码
        
        Args:
            git_url: git仓库URL
            workspace_path: 工作空间路径
            branch_name: 分支名称，默认为master
            token: 访问令牌（可选）
            
        Returns:
            (是否成功, 错误信息)
            
        author  lichaojie
        """
        try:
            project_name = GitUtil.get_project_name_from_url(git_url)
            repo_path = os.path.join(workspace_path, project_name)
            
            # 检查路径长度
            is_safe, warning = GitUtil.check_path_length(repo_path)
            if not is_safe:
                logger.warn(warning)
                # 尝试使用更短的路径
                short_workspace = GitUtil.suggest_short_workspace_path(workspace_path)
                if short_workspace != workspace_path:
                    logger.info(f"尝试使用更短的路径: {short_workspace}")
                    repo_path = os.path.join(short_workspace, project_name)
                    # 确保目录存在
                    os.makedirs(short_workspace, exist_ok=True)
            
            if GitUtil.is_git_repository(repo_path):
                logger.info(f"项目已存在: {repo_path}")
                # 项目存在：切换到指定分支并拉取最新代码
                success, error = GitUtil._update_existing_repository(repo_path, branch_name)
                if not success:
                    return False, error
            else:
                logger.info(f"项目不存在，开始克隆: {git_url}")
                # 项目不存在：克隆项目并切换到指定分支
                success, error = GitUtil._clone_and_setup_repository(git_url, repo_path, branch_name, token)
                if not success:
                    return False, error
            
            logger.info(f"项目准备完成: {repo_path} (分支: {branch_name})")
            return True, ""
            
        except Exception as e:
            error_msg = f"确保仓库存在过程中发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def check_path_length(path: str) -> Tuple[bool, str]:
        """
        检查路径长度是否超过Windows限制
        
        Args:
            path: 要检查的路径
            
        Returns:
            (是否安全, 警告信息)
        """
        if os.name == 'nt':  # Windows系统
            if len(path) > 240:  # 留一些余量
                return False, f"路径长度 ({len(path)} 字符) 可能超过Windows限制 (260字符): {path}"
        return True, ""
    
    @staticmethod
    def suggest_short_workspace_path(workspace_path: str) -> str:
        """
        建议一个更短的工作空间路径
        
        Args:
            workspace_path: 当前工作空间路径
            
        Returns:
            建议的短路径
        """
        if os.name == 'nt':  # Windows系统
            # 尝试使用更短的路径
            if workspace_path.startswith('C:\\Users\\'):
                # 使用环境变量
                username = os.environ.get('USERNAME', 'user')
                return f"C:\\temp\\{username}\\workspace"
            elif len(workspace_path) > 100:
                # 如果路径太长，使用临时目录
                return os.path.join(os.environ.get('TEMP', 'C:\\temp'), 'workspace')
        return workspace_path

    @staticmethod
    def _update_existing_repository(repo_path: str, branch_name: str) -> Tuple[bool, str]:
        """
        更新已存在的仓库：获取远程最新分支信息，强制丢弃本地变更并切换到指定分支
        
        Args:
            repo_path: 仓库路径
            branch_name: 分支名称
            
        Returns:
            (是否成功, 错误信息)
        """
        try:
            logger.info(f"正在更新已存在的仓库: {repo_path}")
            
            # 1. 获取远程最新分支信息
            logger.info("获取远程最新分支信息")
            logger.info("执行git命令: git fetch origin")
            fetch_result = subprocess.run(
                ['git', 'fetch', 'origin'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=60
            )
            
            if fetch_result.returncode != 0:
                error_msg = f"获取远程分支信息失败: {fetch_result.stderr}"
                logger.error(error_msg)
                return False, error_msg
            
            # 2. 强制丢弃本地所有变更
            logger.info("强制丢弃本地所有变更")
            logger.info("执行git命令: git reset --hard HEAD")
            reset_result = subprocess.run(
                ['git', 'reset', '--hard', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30
            )
            
            if reset_result.returncode != 0:
                logger.warn(f"重置本地变更失败: {reset_result.stderr}")
            
            # 3. 清理未跟踪的文件
            logger.info("清理未跟踪的文件")
            logger.info("执行git命令: git clean -fd")
            clean_result = subprocess.run(
                ['git', 'clean', '-fd'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30
            )
            
            if clean_result.returncode != 0:
                logger.warn(f"清理未跟踪文件失败: {clean_result.stderr}")
            
            # 4. 切换到指定分支
            logger.info(f"切换到分支: {branch_name}")
            logger.info(f"执行git命令: git checkout {branch_name}")
            checkout_result = subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30
            )
            
            if checkout_result.returncode != 0:
                # 如果分支不存在，尝试从远程创建
                logger.info(f"本地分支 {branch_name} 不存在，尝试从远程创建")
                logger.info(f"执行git命令: git checkout -b {branch_name} origin/{branch_name}")
                checkout_result = subprocess.run(
                    ['git', 'checkout', '-b', branch_name, f'origin/{branch_name}'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=30
                )
                
                if checkout_result.returncode != 0:
                    error_msg = f"创建并切换到分支 {branch_name} 失败: {checkout_result.stderr}"
                    logger.error(error_msg)
                    return False, error_msg
            
            # 5. 强制重置到远程分支最新状态
            logger.info(f"重置到远程分支最新状态")
            logger.info(f"执行git命令: git reset --hard origin/{branch_name}")
            reset_remote_result = subprocess.run(
                ['git', 'reset', '--hard', f'origin/{branch_name}'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30
            )
            
            if reset_remote_result.returncode != 0:
                logger.warn(f"重置到远程分支失败: {reset_remote_result.stderr}")
            else:
                logger.info("成功重置到远程分支最新状态")
            
            return True, ""
            
        except subprocess.TimeoutExpired:
            error_msg = "更新仓库操作超时"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"更新仓库过程中发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def _clone_and_setup_repository(git_url: str, repo_path: str, branch_name: str, token: Optional[str] = None) -> Tuple[bool, str]:
        """
        克隆新仓库并设置到指定分支
        
        Args:
            git_url: git仓库URL
            repo_path: 目标路径
            branch_name: 分支名称
            token: 访问令牌（可选）
            
        Returns:
            (是否成功, 错误信息)
        """
        try:
            logger.info(f"克隆新仓库: {git_url}")
            
            # 1. 克隆仓库
            success, error = GitUtil.clone_repository(git_url, repo_path, token)
            if not success:
                return False, error
            
            # 2. 切换到指定分支
            logger.info(f"切换到分支: {branch_name}")
            logger.info(f"执行git命令: git checkout {branch_name}")
            checkout_result = subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if checkout_result.returncode != 0:
                # 如果分支不存在，尝试创建并切换到该分支
                logger.info(f"分支 {branch_name} 不存在，尝试创建并切换")
                logger.info(f"执行git命令: git checkout -b {branch_name}")
                checkout_result = subprocess.run(
                    ['git', 'checkout', '-b', branch_name],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if checkout_result.returncode != 0:
                    error_msg = f"创建并切换到分支 {branch_name} 失败: {checkout_result.stderr}"
                    logger.error(error_msg)
                    return False, error_msg
            
            logger.info(f"仓库克隆和分支设置完成: {repo_path}")
            return True, ""
            
        except subprocess.TimeoutExpired:
            error_msg = "克隆和设置仓库操作超时"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"克隆和设置仓库过程中发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
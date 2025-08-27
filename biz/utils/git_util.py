import os
import subprocess
import shutil
from typing import Optional, Tuple, List
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
            
        author  lichaojie
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
                    # HTTP/HTTPS URL，在用户名部分添加token
                    netloc = parsed_url.netloc
                    if '@' in netloc:
                        # 如果URL中已经有用户名，替换用户名部分
                        host_part = netloc.split('@')[-1]
                        git_url_to_use = f"{parsed_url.scheme}://{token}@{host_part}{parsed_url.path}"
                    else:
                        git_url_to_use = f"{parsed_url.scheme}://{token}@{netloc}{parsed_url.path}"
                # 对于SSH URL，我们保持原样，因为token通常不适用于SSH
            
            # 在Ubuntu/Linux环境下进行git配置优化
            if os.name != 'nt':  # 非Windows系统
                # 配置git以优化性能
                GitUtil._execute_git_command(
                    ['git', 'config', '--global', 'core.compression', '0'],
                    timeout=30
                )
                GitUtil._execute_git_command(
                    ['git', 'config', '--global', 'http.postBuffer', '524288000'],
                    timeout=30
                )
                GitUtil._execute_git_command(
                    ['git', 'config', '--global', 'http.lowSpeedLimit', '0'],
                    timeout=30
                )
                GitUtil._execute_git_command(
                    ['git', 'config', '--global', 'http.lowSpeedTime', '999999'],
                    timeout=30
                )
            
            # 在Windows上启用长路径支持
            if os.name == 'nt':  # Windows系统
                # 配置Git支持长路径
                GitUtil._execute_git_command(
                    ['git', 'config', '--global', 'core.longpaths', 'true'],
                    timeout=30
                )
                # 配置Git使用Windows长路径API
                GitUtil._execute_git_command(
                    ['git', 'config', '--global', 'core.protectNTFS', 'false'],
                    timeout=30
                )
            
            # 打印克隆命令
            clone_cmd = f"git clone {git_url_to_use} {target_path}"
            logger.info(f"准备执行克隆命令: {clone_cmd}")
            
            # 执行克隆命令
            success, stdout, stderr = GitUtil._execute_git_command(
                ['git', 'clone', git_url_to_use, target_path],
                timeout=600  # 10分钟超时，适应大仓库
            )
            
            if success:
                logger.info(f"仓库克隆成功: {target_path}")
                return True, ""
            else:
                error_msg = f"克隆失败: {stderr}"
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
            
        author  lichaojie
        """
        try:
            if not GitUtil.is_git_repository(repo_path):
                return False, f"路径 {repo_path} 不是有效的git仓库"
            
            # 切换到指定分支
            success, stdout, stderr = GitUtil._execute_git_command(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                timeout=30
            )
            
            if success:
                logger.info(f"成功切换到分支: {branch_name}")
                return True, ""
            else:
                error_msg = f"切换分支失败: {stderr}"
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
        """·
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
        更新已存在的仓库：切换到指定分支并拉取最新代码
        
        Args:
            repo_path: 仓库路径
            branch_name: 分支名称
            
        Returns:
            (是否成功, 错误信息)
            
        author  lichaojie
        """
        try:
            logger.info(f"正在更新已存在的仓库: {repo_path}")
            
            # 1. 切换到指定分支
            success, stdout, stderr = GitUtil._execute_git_command(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                timeout=30
            )
            
            if not success:
                # 如果分支不存在，尝试创建并切换到该分支
                logger.info(f"分支 {branch_name} 不存在，尝试创建并切换")
                success, stdout, stderr = GitUtil._execute_git_command(
                    ['git', 'checkout', '-b', branch_name],
                    cwd=repo_path,
                    timeout=30
                )
                
                if not success:
                    error_msg = f"创建并切换到分支 {branch_name} 失败: {stderr}"
                    logger.error(error_msg)
                    return False, error_msg
            
            # 2. 拉取最新代码
            success, stdout, stderr = GitUtil._execute_git_command(
                ['git', 'pull', 'origin', branch_name],
                cwd=repo_path,
                timeout=120  # 增加超时时间到2分钟
            )
            
            if not success:
                logger.warn(f"拉取代码失败: {stderr}")
                # 拉取失败不影响整体流程，继续执行
            else:
                logger.info("代码拉取成功")
            
            return True, ""
            
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
            
        author  lichaojie
        """
        try:
            logger.info(f"克隆新仓库: {git_url}")
            
            # 1. 克隆仓库
            success, error = GitUtil.clone_repository(git_url, repo_path, token)
            if not success:
                return False, error
            
            # 2. 切换到指定分支
            success, stdout, stderr = GitUtil._execute_git_command(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                timeout=30
            )
            
            if not success:
                # 如果分支不存在，尝试创建并切换到该分支
                logger.info(f"分支 {branch_name} 不存在，尝试创建并切换")
                success, stdout, stderr = GitUtil._execute_git_command(
                    ['git', 'checkout', '-b', branch_name],
                    cwd=repo_path,
                    timeout=30
                )
                
                if not success:
                    error_msg = f"创建并切换到分支 {branch_name} 失败: {stderr}"
                    logger.error(error_msg)
                    return False, error_msg
            
            logger.info(f"仓库克隆和分支设置完成: {repo_path}")
            return True, ""
            
        except Exception as e:
            error_msg = f"克隆和设置仓库过程中发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    def _execute_git_command(args: List[str], cwd: Optional[str] = None, env: Optional[dict] = None, timeout: int = 300) -> Tuple[bool, str, str]:
        """
        执行git命令并打印完整命令
        
        Args:
            args: git命令参数列表
            cwd: 工作目录
            env: 环境变量
            timeout: 超时时间（秒）
            
        Returns:
            (是否成功, 标准输出, 错误输出)
            
        author  lichaojie
        """
        # 构建完整命令字符串用于打印
        cmd_str = ' '.join(args)
        logger.info(f"执行git命令: {cmd_str}")
        if cwd:
            logger.info(f"工作目录: {cwd}")
        
        try:
            # 设置环境变量
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            # 在Ubuntu/Linux环境下设置一些优化参数
            if os.name != 'nt':  # 非Windows系统
                # 设置git配置以优化性能
                process_env['GIT_TERMINAL_PROGRESS'] = '1'
                process_env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30'
            
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=process_env
            )
            
            if result.returncode == 0:
                logger.info(f"git命令执行成功: {cmd_str}")
                return True, result.stdout, result.stderr
            else:
                logger.error(f"git命令执行失败: {cmd_str}")
                logger.error(f"错误输出: {result.stderr}")
                return False, result.stdout, result.stderr
                
        except subprocess.TimeoutExpired:
            error_msg = f"git命令执行超时: {cmd_str}"
            logger.error(error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"git命令执行异常: {cmd_str}, 错误: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg
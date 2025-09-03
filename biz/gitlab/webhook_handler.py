import os
import re
import time
import base64
from urllib.parse import urljoin, quote
import fnmatch
import requests

from biz.utils.log import logger


def filter_changes(changes: list):
    '''
    过滤数据，只保留支持的文件类型以及必要的字段信息
    '''
    # 从环境变量中获取支持的文件扩展名
    supported_extensions = os.getenv('SUPPORTED_EXTENSIONS', '.java,.py,.php').split(',')

    filter_deleted_files_changes = [change for change in changes if not change.get("deleted_file")]

    # 过滤 `new_path` 以支持的扩展名结尾的元素, 仅保留diff和new_path字段
    filtered_changes = [
        {
            'diff': item.get('diff', ''),
            'new_path': item['new_path'],
            'additions': len(re.findall(r'^\+(?!\+\+)', item.get('diff', ''), re.MULTILINE)),
            'deletions': len(re.findall(r'^-(?!--)', item.get('diff', ''), re.MULTILINE))
        }
        for item in filter_deleted_files_changes
        if any(item.get('new_path', '').endswith(ext) for ext in supported_extensions)
    ]
    return filtered_changes


def slugify_url(original_url: str) -> str:
    """
    将原始URL转换为适合作为文件名的字符串，其中非字母或数字的字符会被替换为下划线，举例：
    slugify_url("http://example.com/path/to/repo/") => example_com_path_to_repo
    slugify_url("https://gitlab.com/user/repo.git") => gitlab_com_user_repo_git
    """
    # Remove URL scheme (http, https, etc.) if present
    original_url = re.sub(r'^https?://', '', original_url)

    # Replace non-alphanumeric characters (except underscore) with underscores
    target = re.sub(r'[^a-zA-Z0-9]', '_', original_url)

    # Remove trailing underscore if present
    target = target.rstrip('_')

    return target


# 用户信息缓存，key为token，value为用户信息
_user_cache = {}


def get_user_info(gitlab_token: str, gitlab_url: str) -> dict:
    """
    获取GitLab用户信息，支持缓存功能
    缓存key为PRIVATE-TOKEN的值
    """
    if not gitlab_token or not gitlab_url:
        logger.warn("GitLab token or URL is empty")
        return {}
    
    # 检查缓存
    if gitlab_token in _user_cache:
        logger.debug(f"User info found in cache for token: {gitlab_token[:10]}...")
        return _user_cache[gitlab_token]
    
    # 调用GitLab API获取用户信息
    url = urljoin(f"{gitlab_url}/", "api/v4/user")
    headers = {
        'Private-Token': gitlab_token
    }
    
    try:
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get user info response from GitLab: {response.status_code}, URL: {url}")
        
        if response.status_code == 200:
            user_info = response.json()
            # 缓存用户信息
            _user_cache[gitlab_token] = user_info
            logger.info(f"User info cached for user: {user_info.get('username', 'unknown')}")
            return user_info
        else:
            logger.warn(f"Failed to get user info: {response.status_code}, {response.text}")
            return {}
    except Exception as e:
        logger.error(f"Error getting user info: {str(e)}")
        return {}


def get_user_id(gitlab_token: str, gitlab_url: str) -> int:
    """
    获取GitLab用户ID，支持缓存功能
    """
    user_info = get_user_info(gitlab_token, gitlab_url)
    return user_info.get('id', 0)

def get_file_content(gitlab_token: str, gitlab_url: str, project_id: int, file_path: str, branch_name: str) -> str:
    """
    获取GitLab文件内容
    
    Args:
        gitlab_token: GitLab私有令牌
        gitlab_url: GitLab服务器URL
        project_id: 项目ID
        file_path: 文件路径（会自动进行URL编码）
        branch_name: 分支名称（会自动进行URL编码）
    
    Returns:
        str: 文件内容，如果获取失败返回空字符串
    
    API示例:
    GET /api/v4/projects/{project_id}/repository/files/{file_path}?ref={branch_name}
    响应包含base64编码的文件内容，需要解码后返回
    """
    if not all([gitlab_token, gitlab_url, project_id, file_path, branch_name]):
        logger.warn("Missing required parameters for get_file_content")
        return ""
    
    # URL编码文件路径和分支名
    encoded_file_path = quote(file_path, safe='')
    encoded_branch_name = quote(branch_name, safe='')
    
    url = urljoin(f"{gitlab_url}/", 
                  f"api/v4/projects/{project_id}/repository/files/{encoded_file_path}?ref={encoded_branch_name}")
    headers = {
        'Private-Token': gitlab_token
    }
    
    try:
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get file content response from GitLab: {response.status_code}, URL: {url}")
        
        if response.status_code == 200:
            file_data = response.json()
            content = file_data.get('content', '')
            encoding = file_data.get('encoding', '')
            
            # 如果是base64编码，需要解码
            if encoding == 'base64' and content:
                try:
                    decoded_content = base64.b64decode(content).decode('utf-8')
                    logger.info(f"Successfully retrieved and decoded file: {file_path}")
                    return decoded_content
                except Exception as decode_error:
                    logger.error(f"Failed to decode file content: {str(decode_error)}")
                    return ""
            else:
                logger.info(f"Successfully retrieved file (no decoding needed): {file_path}")
                return content
        else:
            logger.warn(f"Failed to get file content: {response.status_code}, {response.text}")
            return ""
    except Exception as e:
        logger.error(f"Error getting file content: {str(e)}")
        return ""



class MergeRequestHandler:
    def __init__(self, webhook_data: dict, gitlab_token: str, gitlab_url: str):
        self.merge_request_iid = None
        self.webhook_data = webhook_data
        self.gitlab_token = gitlab_token
        self.gitlab_url = gitlab_url
        self.event_type = None
        self.project_id = None
        self.action = None
        self.parse_event_type()

    def parse_event_type(self):
        # 提取 event_type
        self.event_type = self.webhook_data.get('object_kind', None)
        if self.event_type == 'merge_request':
            self.parse_merge_request_event()

    def parse_merge_request_event(self):
        # 提取 Merge Request 的相关参数
        merge_request = self.webhook_data.get('object_attributes', {})
        self.merge_request_iid = merge_request.get('iid')
        self.project_id = merge_request.get('target_project_id')
        self.action = merge_request.get('action')

    def get_merge_request_changes(self) -> list:
        # 检查是否为 Merge Request Hook 事件
        if self.event_type != 'merge_request':
            logger.warn(f"Invalid event type: {self.event_type}. Only 'merge_request' event is supported now.")
            return []

        # Gitlab merge request changes API可能存在延迟，多次尝试
        max_retries = 3  # 最大重试次数
        retry_delay = 10  # 重试间隔时间（秒）
        for attempt in range(max_retries):
            # 调用 GitLab API 获取 Merge Request 的 changes
            url = urljoin(f"{self.gitlab_url}/",
                          f"api/v4/projects/{self.project_id}/merge_requests/{self.merge_request_iid}/changes")
            headers = {
                'Private-Token': self.gitlab_token
            }
            response = requests.get(url, headers=headers, verify=False)
            logger.debug(
                f"Get changes response from GitLab (attempt {attempt + 1}): {response.status_code}, {response.text}, URL: {url}")

            # 检查请求是否成功
            if response.status_code == 200:
                changes = response.json().get('changes', [])
                if changes:
                    return changes
                else:
                    logger.info(
                        f"Changes is empty, retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries}), URL: {url}")
                    time.sleep(retry_delay)
            else:
                logger.warn(f"Failed to get changes from GitLab (URL: {url}): {response.status_code}, {response.text}")
                return []

        logger.warning(f"Max retries ({max_retries}) reached. Changes is still empty.")
        return []  # 达到最大重试次数后返回空列表

    def get_merge_request_commits(self) -> list:
        # 检查是否为 Merge Request Hook 事件
        if self.event_type != 'merge_request':
            return []

        # 调用 GitLab API 获取 Merge Request 的 commits
        url = urljoin(f"{self.gitlab_url}/",
                      f"api/v4/projects/{self.project_id}/merge_requests/{self.merge_request_iid}/commits")
        headers = {
            'Private-Token': self.gitlab_token
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get commits response from gitlab: {response.status_code}, {response.text}")
        # 检查请求是否成功
        if response.status_code == 200:
            return response.json()
        else:
            logger.warn(f"Failed to get commits: {response.status_code}, {response.text}")
            return []

    def add_merge_request_notes(self, review_result):
        url = urljoin(f"{self.gitlab_url}/",
                      f"api/v4/projects/{self.project_id}/merge_requests/{self.merge_request_iid}/notes")
        headers = {
            'Private-Token': self.gitlab_token,
            'Content-Type': 'application/json'
        }
        data = {
            'body': review_result
        }
        response = requests.post(url, headers=headers, json=data, verify=False)
        logger.debug(f"Add notes to gitlab {url}: {response.status_code}, {response.text}")
        if response.status_code == 201:
            logger.info("Note successfully added to merge request.")
        else:
            logger.error(f"Failed to add note: {response.status_code}")
            logger.error(response.text)

    def target_branch_protected(self) -> bool:
        url = urljoin(f"{self.gitlab_url}/",
                      f"api/v4/projects/{self.project_id}/protected_branches")
        headers = {
            'Private-Token': self.gitlab_token,
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get protected branches response from gitlab: {response.status_code}, {response.text}")
        # 检查请求是否成功
        if response.status_code == 200:
            data = response.json()
            target_branch = self.webhook_data['object_attributes']['target_branch']
            return any(fnmatch.fnmatch(target_branch, item['name']) for item in data)
        else:
            logger.warn(f"Failed to get protected branches: {response.status_code}, {response.text}")
            return False

    def get_current_user_id(self) -> int:
        """获取当前GitLab用户ID"""
        return get_user_id(self.gitlab_token, self.gitlab_url)

    def get_current_user_info(self) -> dict:
        """获取当前GitLab用户信息"""
        return get_user_info(self.gitlab_token, self.gitlab_url)

    def get_merge_request_notes(self) -> list:
        """获取 Merge Request 的评论列表"""
        if self.event_type != 'merge_request':
            logger.warn(f"Invalid event type: {self.event_type}. Only 'merge_request' event is supported now.")
            return []

        url = urljoin(f"{self.gitlab_url}/",
                      f"api/v4/projects/{self.project_id}/merge_requests/{self.merge_request_iid}/notes?page=1&per_page=100")
        headers = {
            'Private-Token': self.gitlab_token
        }
        
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(f"Get notes response from GitLab: {response.status_code}, URL: {url}")
        
        if response.status_code == 200:
            notes = response.json()
            logger.info(f"Successfully retrieved {len(notes)} notes from merge request.")
            return notes
        else:
            logger.warn(f"Failed to get notes from GitLab: {response.status_code}, {response.text}")
            return []

    def delete_current_user_notes(self) -> int:
        """删除当前用户的非系统评论"""
        if self.event_type != 'merge_request':
            logger.warn(f"Invalid event type: {self.event_type}. Only 'merge_request' event is supported now.")
            return 0

        # 获取当前用户ID
        current_user_id = self.get_current_user_id()
        if not current_user_id:
            logger.warn("Failed to get current user ID")
            return 0

        # 获取所有评论
        notes = self.get_merge_request_notes()
        if not notes:
            logger.info("No notes found to delete")
            return 0

        # 过滤出需要删除的评论（system=false 且 author.id=当前用户ID）
        notes_to_delete = [
            note for note in notes
            if not  note.get('system',True) and note.get('author', {}).get('id') == current_user_id
        ]

        if not notes_to_delete:
            logger.info("No notes found matching deletion criteria")
            return 0

        deleted_count = 0
        for note in notes_to_delete:
            note_id = note.get('id')
            if self._delete_single_note(note_id):
                deleted_count += 1

        logger.info(f"Successfully deleted {deleted_count} out of {len(notes_to_delete)} notes")
        return deleted_count

    def _delete_single_note(self, note_id: int) -> bool:
        """删除单个评论"""
        url = urljoin(f"{self.gitlab_url}/",
                      f"api/v4/projects/{self.project_id}/merge_requests/{self.merge_request_iid}/notes/{note_id}")
        headers = {
            'Private-Token': self.gitlab_token
        }

        response = requests.delete(url, headers=headers, verify=False)
        logger.debug(f"Delete note {note_id} response from GitLab: {response.status_code}, URL: {url}")

        if response.status_code == 204:
            logger.info(f"Successfully deleted note {note_id}")
            return True
        else:
            logger.warn(f"Failed to delete note {note_id}: {response.status_code}, {response.text}")
            return False

    def get_file_content(self, file_path: str, branch_name: str) -> str:
        """获取文件内容"""
        return get_file_content(self.gitlab_token, self.gitlab_url, self.project_id, file_path, branch_name)


class PushHandler:
    def __init__(self, webhook_data: dict, gitlab_token: str, gitlab_url: str):
        self.webhook_data = webhook_data
        self.gitlab_token = gitlab_token
        self.gitlab_url = gitlab_url
        self.event_type = None
        self.project_id = None
        self.branch_name = None
        self.commit_list = []
        self.parse_event_type()

    def parse_event_type(self):
        # 提取 event_type
        self.event_type = self.webhook_data.get('event_name', None)
        if self.event_type == 'push':
            self.parse_push_event()

    def parse_push_event(self):
        # 提取 Push 事件的相关参数
        self.project_id = self.webhook_data.get('project', {}).get('id')
        self.branch_name = self.webhook_data.get('ref', '').replace('refs/heads/', '')
        self.commit_list = self.webhook_data.get('commits', [])

    def get_push_commits(self) -> list:
        # 检查是否为 Push 事件
        if self.event_type != 'push':
            logger.warn(f"Invalid event type: {self.event_type}. Only 'push' event is supported now.")
            return []

        # 提取提交信息
        commit_details = []
        for commit in self.commit_list:
            commit_info = {
                'message': commit.get('message'),
                'author': commit.get('author', {}).get('name'),
                'timestamp': commit.get('timestamp'),
                'url': commit.get('url'),
            }
            commit_details.append(commit_info)

        logger.info(f"Collected {len(commit_details)} commits from push event.")
        return commit_details

    def add_push_notes(self, message: str):
        # 添加评论到 GitLab Push 请求的提交中（此处假设是在最后一次提交上添加注释）
        if not self.commit_list:
            logger.warn("No commits found to add notes to.")
            return

        # 获取最后一个提交的ID
        last_commit_id = self.commit_list[-1].get('id')
        if not last_commit_id:
            logger.error("Last commit ID not found.")
            return

        url = urljoin(f"{self.gitlab_url}/",
                      f"api/v4/projects/{self.project_id}/repository/commits/{last_commit_id}/comments")
        headers = {
            'Private-Token': self.gitlab_token,
            'Content-Type': 'application/json'
        }
        data = {
            'note': message
        }
        response = requests.post(url, headers=headers, json=data, verify=False)
        logger.debug(f"Add comment to commit {last_commit_id}: {response.status_code}, {response.text}")
        if response.status_code == 201:
            logger.info("Comment successfully added to push commit.")
        else:
            logger.error(f"Failed to add comment: {response.status_code}")
            logger.error(response.text)

    def __repository_commits(self, ref_name: str = "", since: str = "", until: str = "", pre_page: int = 100,
                             page: int = 1):
        # 获取仓库提交信息
        url = f"{urljoin(f'{self.gitlab_url}/', f'api/v4/projects/{self.project_id}/repository/commits')}?ref_name={ref_name}&since={since}&until={until}&per_page={pre_page}&page={page}"
        headers = {
            'Private-Token': self.gitlab_token
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(
            f"Get commits response from GitLab for repository_commits: {response.status_code}, {response.text}, URL: {url}")

        if response.status_code == 200:
            return response.json()
        else:
            logger.warn(
                f"Failed to get commits for ref {ref_name}: {response.status_code}, {response.text}")
            return []

    def get_parent_commit_id(self, commit_id: str) -> str:
        commits = self.__repository_commits(ref_name=commit_id, pre_page=1, page=1)
        if commits and commits[0].get('parent_ids', []):
            return commits[0].get('parent_ids', [])[0]
        return ""

    def repository_compare(self, before: str, after: str):
        # 比较两个提交之间的差异
        url = f"{urljoin(f'{self.gitlab_url}/', f'api/v4/projects/{self.project_id}/repository/compare')}?from={before}&to={after}"
        headers = {
            'Private-Token': self.gitlab_token
        }
        response = requests.get(url, headers=headers, verify=False)
        logger.debug(
            f"Get changes response from GitLab for repository_compare: {response.status_code}, {response.text}, URL: {url}")

        if response.status_code == 200:
            return response.json().get('diffs', [])
        else:
            logger.warn(
                f"Failed to get changes for repository_compare: {response.status_code}, {response.text}")
            return []

    def get_push_changes(self) -> list:
        # 检查是否为 Push 事件
        if self.event_type != 'push':
            logger.warn(f"Invalid event type: {self.event_type}. Only 'push' event is supported now.")
            return []

        # 如果没有提交，返回空列表
        if not self.commit_list:
            logger.info("No commits found in push event.")
            return []
        headers = {
            'Private-Token': self.gitlab_token
        }

        # 优先尝试compare API获取变更
        before = self.webhook_data.get('before', '')
        after = self.webhook_data.get('after', '')
        if before and after:
            if after.startswith('0000000'):
                # 删除分支处理
                return []
            if before.startswith('0000000'):
                # 创建分支处理
                first_commit_id = self.commit_list[0].get('id')
                parent_commit_id = self.get_parent_commit_id(first_commit_id)
                if parent_commit_id:
                    before = parent_commit_id
            return self.repository_compare(before, after)
        else:
            return []

    def get_current_user_id(self) -> int:
        """获取当前GitLab用户ID"""
        return get_user_id(self.gitlab_token, self.gitlab_url)

    def get_current_user_info(self) -> dict:
        """获取当前GitLab用户信息"""
        return get_user_info(self.gitlab_token, self.gitlab_url)

    def get_file_content(self, file_path: str, branch_name: str) -> str:
        """获取文件内容"""
        return get_file_content(self.gitlab_token, self.gitlab_url, self.project_id, file_path, branch_name)

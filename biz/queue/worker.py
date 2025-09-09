import os
import traceback
from datetime import datetime
import re
import random
from biz.entity.review_entity import MergeRequestReviewEntity, PushReviewEntity,MergeRequestReviewChainEntity
from biz.event.event_manager import event_manager
from biz.gitlab.webhook_handler import filter_changes, MergeRequestHandler, PushHandler
from biz.github.webhook_handler import filter_changes as filter_github_changes, PullRequestHandler as GithubPullRequestHandler, PushHandler as GithubPushHandler
from biz.service.review_service import ReviewService
from biz.service.call_chain_analysis_service import CallChainAnalysisService
from biz.utils.code_reviewer import CodeReviewer
from biz.utils.im import notifier
from biz.utils.log import logger
from biz.service.call_chain_analysis.pmd_report_formatter import PMDReportFormatter
from biz.service.call_chain_analysis.json_to_md import JsonToMdConverter
from biz.utils.xml_parser import XmlParser
import json



def handle_push_event(webhook_data: dict, gitlab_token: str, gitlab_url: str, gitlab_url_slug: str):
    push_review_enabled = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'
    try:
        handler = PushHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info('Push Hook event received')
        commits = handler.get_push_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        if push_review_enabled:
            # 获取PUSH的changes
            changes = handler.get_push_changes()
            logger.info('changes: %s', changes)
            changes = filter_changes(changes)
            if not changes:
                logger.info('未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
                review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)
                score = CodeReviewer.parse_review_score(review_text=review_result)
                for item in changes:
                    additions += item['additions']
                    deletions += item['deletions']
            # 将review结果提交到Gitlab的 notes
            handler.add_push_notes(f'{review_result}')

        event_manager['push_reviewed'].send(PushReviewEntity(
            project_name=webhook_data['project']['name'],
            author=webhook_data['user_username'],
            branch=webhook_data.get('ref', '').replace('refs/heads/', ''),
            updated_at=int(datetime.now().timestamp()),  # 当前时间
            commits=commits,
            score=score,
            review_result=review_result,
            url_slug=gitlab_url_slug,
            webhook_data=webhook_data,
            additions=additions,
            deletions=deletions,
        ))

    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_merge_request_event(webhook_data: dict, gitlab_token: str, gitlab_url: str, gitlab_url_slug: str):
    '''
    处理Merge Request Hook事件
    :param webhook_data:
    :param gitlab_token:
    :param gitlab_url:
    :param gitlab_url_slug:
    :return:
    '''
    merge_review_only_protected_branches = os.environ.get('MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED', '0') == '1'
    mr_active_target_branches = os.environ.get('MR_ACTIVE_TARGET_BRANCHES', 'prod')
    try:
        project_name = webhook_data['project']["name"]
        # 解析Webhook数据
        handler = MergeRequestHandler(webhook_data, gitlab_token, gitlab_url)
        logger.info(f'Merge Request Hook event received project name is {project_name}')

        # 新增：判断是否为draft（草稿）MR
        object_attributes = webhook_data.get('object_attributes', {})
        is_draft = object_attributes.get('draft') or object_attributes.get('work_in_progress')
        if is_draft:
            msg = f"[通知] MR为草稿（draft），未触发AI审查。\n项目: {webhook_data['project']['name']}\n作者: {webhook_data['user']['username']}\n源分支: {object_attributes.get('source_branch')}\n目标分支: {object_attributes.get('target_branch')}\n链接: {object_attributes.get('url')}"
            # notifier.send_notification(content=msg)
            logger.info(f"MR为draft，仅log，不触发AI review。 {msg}")
            return

        # 如果开启了仅review projected branches的，判断当前目标分支是否为projected branches
        if merge_review_only_protected_branches and not handler.target_branch_protected():
            logger.info("Merge Request target branch not match protected branches, ignored.")
            return

        target_branch =  webhook_data['object_attributes']['target_branch']
        if target_branch not in mr_active_target_branches:
            logger.info(f"target_branch {target_branch}  跳过审查 不在env.MR_ACTIVE_TARGET_BRANCHES  {mr_active_target_branches} ")
            return

        if handler.action not in ['open', 'update']:
            logger.info(f"Merge Request Hook event, action={handler.action}, ignored.")
            return

        # 检查last_commit_id是否已经存在，如果存在则跳过处理
        last_commit_id = object_attributes.get('last_commit', {}).get('id', '')
        if last_commit_id:
            project_name = webhook_data['project']['name']
            source_branch = object_attributes.get('source_branch', '')
            target_branch = object_attributes.get('target_branch', '')
            #todo lcj  调试期间临时不开启
            # if ReviewService.check_mr_last_commit_id_exists(project_name, source_branch, target_branch, last_commit_id):
            #     logger.info(f"Merge Request with last_commit_id {last_commit_id} already exists, skipping review for {project_name}.")
            #     return

        # 仅仅在MR创建或更新时进行Code Review
        # 获取Merge Request的changes
        changes = handler.get_merge_request_changes()
        logger.info('changes: %s', changes)
        changes = filter_changes(changes)
        if not changes:
            logger.info('未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            return


        # 启用调用链分析变更代码对其他方法的影响
        if os.environ.get('CODE_ANALYSIS_ENABLED', '0') == '1':
            _process_change_analysis(webhook_data, gitlab_token, changes, handler)

        # 统计本次新增、删除的代码总数
        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get('additions', 0)
            deletions += item.get('deletions', 0)

        # 获取Merge Request的commits
        # commits = handler.get_merge_request_commits()
        # if not commits:
        #     logger.error('Failed to get commits')
        #     return

        # review 代码
        # commits_text = ';'.join(commit['title'] for commit in commits)
        review_result = CodeReviewer().review_and_strip_code(str(changes), "")

        # 将review结果提交到Gitlab的 notes
        handler.add_merge_request_notes(f'Auto Review Result: \n{review_result})')

        review_finish_notice = mr_finish_notice_content(webhook_data)

        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name= webhook_data['project']['name'],
                author=webhook_data['user']['username'],
                source_branch=webhook_data['object_attributes']['source_branch'],
                target_branch=webhook_data['object_attributes']['target_branch'],
                updated_at=int(datetime.now().timestamp()),
                commits="",
                score=CodeReviewer.parse_review_score(review_text=review_result),
                url=webhook_data['object_attributes']['url'],
                review_result=review_finish_notice,
                url_slug=gitlab_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=last_commit_id,
            )
        )

    except Exception as e:
        error_message = f'AI Code Review 服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def mr_finish_notice_content(webhook_data):
    project_name = webhook_data['project']['name']
    title = webhook_data['object_attributes']['title']
    mr_url = webhook_data['object_attributes']['url']
    mr_direction = webhook_data['object_attributes']['source_branch'] + ' -> ' + webhook_data['object_attributes'][
        'target_branch']
    created_at = webhook_data['object_attributes']['created_at']
    author = webhook_data['user']['username']
    review_finish_notice = f"项目: {project_name} \n合并: {mr_direction} \n标题: {title} \n作者: {author}  {created_at} \n\nMR地址: \n{mr_url}"
    return review_finish_notice


def handle_github_push_event(webhook_data: dict, github_token: str, github_url: str, github_url_slug: str):
    push_review_enabled = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'
    try:
        handler = GithubPushHandler(webhook_data, github_token, github_url)
        logger.info('GitHub Push event received')
        commits = handler.get_push_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        review_result = None
        score = 0
        additions = 0
        deletions = 0
        if push_review_enabled:
            # 获取PUSH的changes
            changes = handler.get_push_changes()
            logger.info('changes: %s', changes)
            changes = filter_github_changes(changes)
            if not changes:
                logger.info('未检测到PUSH代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            review_result = "关注的文件没有修改"

            if len(changes) > 0:
                commits_text = ';'.join(commit.get('message', '').strip() for commit in commits)
                review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)
                score = CodeReviewer.parse_review_score(review_text=review_result)
                for item in changes:
                    additions += item.get('additions', 0)
                    deletions += item.get('deletions', 0)
            # 将review结果提交到GitHub的 notes
            handler.add_push_notes(f'Auto Review Result: \n{review_result}')

        event_manager['push_reviewed'].send(PushReviewEntity(
            project_name=webhook_data['repository']['name'],
            author=webhook_data['sender']['login'],
            branch=webhook_data['ref'].replace('refs/heads/', ''),
            updated_at=int(datetime.now().timestamp()),  # 当前时间
            commits=commits,
            score=score,
            review_result=review_result,
            url_slug=github_url_slug,
            webhook_data=webhook_data,
            additions=additions,
            deletions=deletions,
        ))

    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def handle_github_pull_request_event(webhook_data: dict, github_token: str, github_url: str, github_url_slug: str):
    '''
    处理GitHub Pull Request 事件
    :param webhook_data:
    :param github_token:
    :param github_url:
    :param github_url_slug:
    :return:
    '''
    merge_review_only_protected_branches = os.environ.get('MERGE_REVIEW_ONLY_PROTECTED_BRANCHES_ENABLED', '0') == '1'
    try:
        # 解析Webhook数据
        handler = GithubPullRequestHandler(webhook_data, github_token, github_url)
        logger.info('GitHub Pull Request event received')
        # 如果开启了仅review projected branches的，判断当前目标分支是否为projected branches
        if merge_review_only_protected_branches and not handler.target_branch_protected():
            logger.info("Merge Request target branch not match protected branches, ignored.")
            return

        if handler.action not in ['opened', 'synchronize']:
            logger.info(f"Pull Request Hook event, action={handler.action}, ignored.")
            return

        # 检查GitHub Pull Request的last_commit_id是否已经存在，如果存在则跳过处理
        github_last_commit_id = webhook_data['pull_request']['head']['sha']
        if github_last_commit_id:
            project_name = webhook_data['repository']['name']
            source_branch = webhook_data['pull_request']['head']['ref']
            target_branch = webhook_data['pull_request']['base']['ref']
            
            if ReviewService.check_mr_last_commit_id_exists(project_name, source_branch, target_branch, github_last_commit_id):
                logger.info(f"Pull Request with last_commit_id {github_last_commit_id} already exists, skipping review for {project_name}.")
                return

        # 仅仅在PR创建或更新时进行Code Review
        # 获取Pull Request的changes
        changes = handler.get_pull_request_changes()
        logger.info('changes: %s', changes)
        changes = filter_github_changes(changes)
        if not changes:
            logger.info('未检测到有关代码的修改,修改文件可能不满足SUPPORTED_EXTENSIONS。')
            return
        # 统计本次新增、删除的代码总数
        additions = 0
        deletions = 0
        for item in changes:
            additions += item.get('additions', 0)
            deletions += item.get('deletions', 0)

        # 获取Pull Request的commits
        commits = handler.get_pull_request_commits()
        if not commits:
            logger.error('Failed to get commits')
            return

        # review 代码
        commits_text = ';'.join(commit['title'] for commit in commits)
        review_result = CodeReviewer().review_and_strip_code(str(changes), commits_text)

        # 将review结果提交到GitHub的 notes
        pr_url = webhook_data['pull_request']['html_url']
        handler.add_pull_request_notes(f'Auto Review Result: \n{review_result}\n\nPR地址: {pr_url}')

        # dispatch pull_request_reviewed event
        event_manager['merge_request_reviewed'].send(
            MergeRequestReviewEntity(
                project_name=webhook_data['repository']['name'],
                author=webhook_data['pull_request']['user']['login'],
                source_branch=webhook_data['pull_request']['head']['ref'],
                target_branch=webhook_data['pull_request']['base']['ref'],
                updated_at=int(datetime.now().timestamp()),
                commits=commits,
                score=CodeReviewer.parse_review_score(review_text=review_result),
                url=webhook_data['pull_request']['html_url'],
                review_result=review_result,
                url_slug=github_url_slug,
                webhook_data=webhook_data,
                additions=additions,
                deletions=deletions,
                last_commit_id=github_last_commit_id,
            ))

    except Exception as e:
        error_message = f'服务出现未知错误: {str(e)}\n{traceback.format_exc()}'
        notifier.send_notification(content=error_message)
        logger.error('出现未知错误: %s', error_message)


def _process_change_analysis(webhook_data: dict, gitlab_token: str, changes: list, handler):
    """
    处理调用链分析
    流程图：doc/调用链影响分析.md

    调用链分析结果报告因为根据变更产生，此处只进行代码仓库的评论，外部群暂不进行推送

    Args:
        webhook_data: GitLab webhook数据
        gitlab_token: GitLab访问令牌
        changes: 代码变更列表
        handler: MergeRequestHandler实例
        gitlab_url_slug: GitLab URL标识
        last_commit_id: 最后提交ID
    """
    # 删除历史评论
    handler.delete_current_user_notes()

    # 获取调用链分析结果
    changes_prompt_json = CallChainAnalysisService.process(webhook_data, gitlab_token, changes, handler)
    
    # 如果没有分析结果，直接返回
    if changes_prompt_json is None:
        logger.info("没有调用链分析数据，跳过调用链分析")
        return

    # 获取最大处理项目数量配置
    max_items = int(os.environ.get('CODE_ANALYSIS_MAX_ITEM', '25'))
    
    # 如果超过最大数量，随机选择
    items_to_process = list(changes_prompt_json.items())
    if len(items_to_process) > max_items:
        items_to_process = random.sample(items_to_process, max_items)
        logger.info(f"变更项目数量 {len(changes_prompt_json)} 超过配置上限 {max_items}，随机选择 {max_items} 个进行处理")
    
    # 遍历选中的items，循环执行代码审查
    logger.info(f"开始处理调用链分析，包含 {len(items_to_process)} 个变更的提示词")

    # 第一步：收集所有review_result的JSON数据
    all_review_results = []
    
    for change_index, content in items_to_process:
        prompt = content['prompt']
        if not prompt or not prompt.strip():  # 确保提示词不为空
            logger.info(f"Change {change_index} 的提示词为空，跳过处理")
            continue
            
        logger.info(f"开始处理Change {change_index} 的调用链分析")

        # 执行调用链代码审查
        review_result = CodeReviewer().review_and_analyze_call_chain_code(prompt, content['language'])

        # 解析XML格式的review_result并收集
        if review_result and review_result.strip():
            try:
                items = XmlParser.parse_review_items(review_result)
                gitlab_url = PMDReportFormatter._convert_to_gitlab_url_by_path(content['file_path'], webhook_data)
                # 为每个item添加GitLab链接
                for item in items:
                    item['name'] = f"[{item['name']}]({gitlab_url})"
                    all_review_results.append(item)
                    
            except Exception as e:
                logger.error(f"解析XML格式错误 跳过此项: {e}")

    # 根据项目配置过滤问题级别
    filtered_review_result = _filter_review_result_by_project_level(
            webhook_data['project']['name'],
            all_review_results)

    # 第二步：循环完成后，生成AI审查报告并发送
    if filtered_review_result:
        # 使用工具类生成Markdown格式的AI审查报告
        ai_review_report = JsonToMdConverter.convert_review_results_to_md(filtered_review_result)
        handler.add_merge_request_notes(ai_review_report)

        # 问题修正报告
        ai_review_report = JsonToMdConverter.issue_fix_suggestion_to_md(filtered_review_result)
        handler.add_merge_request_notes(ai_review_report)

        logger.info(f"调用链分析完成，共处理 {len(filtered_review_result)} 个审查结果")
    else:
        logger.info("没有发现需要审查的问题，跳过报告生成")





def _filter_review_result_by_project_level(project_name: str, review_results: list) -> list:
    """
    根据项目配置过滤问题级别
    
    Args:
        project_name: 项目名称
        review_results: 审查结果列表，每个元素是包含name、issue、level、content的dict
        
    Returns:
        过滤后的审查结果列表
    """
    # 获取环境变量配置
    default_level = os.environ.get('CODE_ANALYSIS_CHANGE_AI_LEVEL_DEFAULT', 'LOW')
    high_projects = os.environ.get('CODE_ANALYSIS_CHANGE_AI_LEVEL_HIGH', '').split(',')
    middle_projects = os.environ.get('CODE_ANALYSIS_CHANGE_AI_LEVEL_MIDDLE', '').split(',')
    low_projects = os.environ.get('CODE_ANALYSIS_CHANGE_AI_LEVEL_LOW', '').split(',')
    
    # 确定项目级别
    project_level = default_level
    if project_name in high_projects:
        project_level = 'HIGH'
    elif project_name in middle_projects:
        project_level = 'MIDDLE'
    elif project_name in low_projects:
        project_level = 'LOW'

    logger.info(f"项目 {project_name} 使用级别: {project_level}")
    
    # 根据级别过滤结果
    if project_level == 'HIGH':
        # 只显示高级别问题
        return [item for item in review_results if '🔴 高' in item.get('level', '')]
    elif project_level == 'MIDDLE':
        # 显示中高级别问题
        return [item for item in review_results if '🔴 高' in item.get('level', '') or '🟡 中' in item.get('level', '')]
    elif project_level == 'LOW':
        # 全显示
        return review_results


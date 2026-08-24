"""敏感词规则数据访问 mixin - 供 DatabaseManager 组合"""
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from ..models import SensitiveWordRule, MessageFilterLog


class SensitiveRulesMixin:
    """敏感词规则相关数据库操作"""

    def add_sensitive_word_rule(self, keyword: str, action: str = "block", replacement: str = None,
                               category: str = "general", severity: str = "medium",
                               description: str = "") -> dict:
        """添加敏感词规则

        Returns:
            {"success": bool, "rule": dict, "message": str}
        """
        session = self.get_session()
        try:
            # 检查关键词是否已存在
            existing_rule = session.query(SensitiveWordRule).filter(
                SensitiveWordRule.keyword == keyword
            ).first()

            if existing_rule:
                return {"success": False, "message": f"敏感词 '{keyword}' 已存在"}

            # 创建新规则
            new_rule = SensitiveWordRule(
                keyword=keyword,
                action=action,
                replacement=replacement,
                category=category,
                severity=severity,
                description=description,
                status="active"
            )

            session.add(new_rule)
            session.commit()
            session.refresh(new_rule)

            logger.info(f"敏感词规则添加成功: {keyword} ({action})")
            return {"success": True, "rule": new_rule.to_dict(), "message": "敏感词规则添加成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"添加敏感词规则失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

    def get_all_sensitive_rules(self) -> list[dict]:
        """获取所有敏感词规则"""
        session = self.get_session()
        try:
            rules = session.query(SensitiveWordRule).order_by(SensitiveWordRule.updated_at.desc()).all()
            return [rule.to_dict() for rule in rules]
        except SQLAlchemyError as e:
            logger.error(f"获取敏感词规则列表失败: {e}")
            return []
        finally:
            self.close_session(session)

    def update_sensitive_rule(self, rule_id: int, **kwargs) -> dict:
        """更新敏感词规则

        Returns:
            {"success": bool, "rule": dict, "message": str}
        """
        session = self.get_session()
        try:
            rule = session.query(SensitiveWordRule).filter(SensitiveWordRule.id == rule_id).first()
            if not rule:
                return {"success": False, "message": "敏感词规则未找到"}

            # 更新字段
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)

            session.commit()
            session.refresh(rule)

            logger.info(f"敏感词规则更新成功: {rule.keyword}")
            return {"success": True, "rule": rule.to_dict(), "message": "敏感词规则更新成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"更新敏感词规则失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

    def delete_sensitive_rule(self, rule_id: int) -> dict:
        """删除敏感词规则

        Returns:
            {"success": bool, "message": str}
        """
        session = self.get_session()
        try:
            rule = session.query(SensitiveWordRule).filter(SensitiveWordRule.id == rule_id).first()
            if not rule:
                return {"success": False, "message": "敏感词规则未找到"}

            session.delete(rule)
            session.commit()

            logger.info(f"敏感词规则删除成功: {rule.keyword}")
            return {"success": True, "message": "敏感词规则删除成功"}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"删除敏感词规则失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

    def filter_message(self, content: str) -> dict:
        """过滤消息内容

        Returns:
            {
                "passed": bool,           # 是否通过
                "filtered_content": str,  # 过滤后的内容
                "matched_rules": list,    # 匹配到的规则
                "action_taken": str       # 采取的动作
            }
        """
        session = self.get_session()
        try:
            # 获取所有活跃的敏感词规则
            active_rules = session.query(SensitiveWordRule).filter(
                SensitiveWordRule.status == "active"
            ).all()

            filtered_content = content
            matched_rules = []
            action_taken = "pass"  # 默认通过

            for rule in active_rules:
                if rule.keyword in content:
                    matched_rules.append({
                        "rule_id": rule.id,
                        "keyword": rule.keyword,
                        "action": rule.action,
                        "replacement": rule.replacement
                    })

                    # 根据规则动作处理
                    if rule.action == "block":
                        action_taken = "block"
                        filtered_content = "[消息包含敏感词，已被拦截]"
                        break  # 遇到block规则立即终止
                    elif rule.action in ("replace", "mask"):
                        # mask 与 replace 语义一致：用 replacement 掩盖敏感词（缺省 ***）
                        action_taken = rule.action
                        replacement = rule.replacement if rule.replacement else "***"
                        filtered_content = filtered_content.replace(rule.keyword, replacement)
                    elif rule.action == "review":
                        action_taken = "review"
                        filtered_content = f"[待审核: {filtered_content}]"

            # replace/mask 属于"放行但脱敏"，其余（block/review）视为未通过
            passed = action_taken in ["pass", "replace", "mask"]

            return {
                "passed": passed,
                "filtered_content": filtered_content,
                "matched_rules": matched_rules,
                "action_taken": action_taken
            }

        except SQLAlchemyError as e:
            logger.error(f"过滤消息失败: {e}")
            # 出错时默认通过
            return {
                "passed": True,
                "filtered_content": content,
                "matched_rules": [],
                "action_taken": "error"
            }
        finally:
            self.close_session(session)

    def log_filter_action(self, message_id: int, rule_id: int, matched_word: str,
                         action_taken: str, original_content: str, filtered_content: str) -> dict:
        """记录过滤日志

        Returns:
            {"success": bool}
        """
        session = self.get_session()
        try:
            log_entry = MessageFilterLog(
                message_id=message_id,
                rule_id=rule_id,
                matched_word=matched_word,
                action_taken=action_taken,
                original_content=original_content,
                filtered_content=filtered_content
            )

            session.add(log_entry)
            session.commit()

            return {"success": True}

        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"记录过滤日志失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close_session(session)

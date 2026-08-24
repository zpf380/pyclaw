#!/usr/bin/env python3
"""
调试敏感词过滤逻辑
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pyclaw'))

from pyclaw.database.database import DatabaseManager

def debug_filter():
    """调试过滤逻辑"""
    
    # 初始化数据库管理器
    db_manager = DatabaseManager("sqlite:///debug_filter.db")
    
    try:
        # 创建测试数据库表
        db_manager.create_tables()
        print("[OK] 数据库表创建成功")
        
        # 添加测试敏感词规则
        test_rules = [
            {
                "keyword": "敏感词",
                "action": "block",
                "category": "test",
                "severity": "high",
                "description": "测试拦截规则"
            }
        ]
        
        print("\n[ADD] 添加测试敏感词规则...")
        for rule_data in test_rules:
            result = db_manager.add_sensitive_word_rule(**rule_data)
            if result["success"]:
                print(f"[OK] 添加规则成功: {rule_data['keyword']} -> {rule_data['action']}")
            else:
                print(f"[ERROR] 添加规则失败: {result.get('message', result.get('error', '未知错误'))}")
        
        # 测试特定消息
        test_messages = [
            "这是一条正常的消息，没有敏感词",
            "敏感词",
            "包含敏感词的消息",
            "没有问题的消息"
        ]
        
        print("\n[DEBUG] 调试过滤逻辑...")
        
        for message in test_messages:
            print(f"\n测试消息: {message}")
            print(f"是否包含'敏感词': {'是' if '敏感词' in message else '否'}")
            
            result = db_manager.filter_message(message)
            print(f"过滤结果: {result}")
            
    except Exception as e:
        print(f"[ERROR] 调试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理测试数据库
        if os.path.exists("debug_filter.db"):
            try:
                os.remove("debug_filter.db")
                print("\n[CLEAN] 已清理测试数据库")
            except PermissionError:
                print("\n[WARNING] 无法删除测试数据库，文件可能被占用")

if __name__ == "__main__":
    debug_filter()
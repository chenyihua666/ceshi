"""
NL2SQL：自然语言转 SQL 并执行，支持 SELECT/INSERT/UPDATE/DELETE + 结果润色
"""
import os
import json
import pymysql
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ========== LLM 配置 ==========
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen3.7-plus"


def call_llm(prompt: str) -> str:
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


# ========== 数据库配置 ==========
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', '123456'),
    'database': os.getenv('DB_NAME', 'test'),
    'charset': 'utf8mb4'
}

# ========== 表结构描述 ==========
SCHEMA = """
数据库中有以下表：

1. users 表（用户信息）:
    -id: INT, 主键, 自增
    -name: VARCHAR(50), 用户名
    -age: INT, 年龄
    -email: VARCHAR(100), 邮箱
    -city: VARCHAR(50), 所在城市
    -created_at: DATETIME, 创建时间

2. orders 表（订单信息）:
    -id: INT, 主键, 自增
    -user_id: INT, 外键，关联 users.id
    -product: VARCHAR(100), 商品名称
    -amount: DECIMAL(10,2), 订单金额
    -status: VARCHAR(20), 状态（pending/paid/shipped/cancelled）
    -order_date: DATETIME, 下单时间

关系：一个用户有多条订单记录（users.id = orders.user_id，一对多）
"""

# ========== Few-shot 训练样本 ==========
EXAMPLES = """
示例 1：
问题：查询所有用户
SQL：SELECT * FROM users

示例 2：
问题：张三买了什么东西？
SQL：SELECT u.name, o.product, o.amount, o.status FROM users u JOIN orders o ON u.id = o.user_id WHERE u.name = '张三'

示例 3：
问题：北京的用户的订单总金额是多少？
SQL：SELECT u.name, SUM(o.amount) as total FROM users u JOIN orders o ON u.id = o.user_id WHERE u.city = '北京' GROUP BY u.id, u.name

示例 4：
问题：添加一个叫李四的用户，25岁
SQL：INSERT INTO users (name, age) VALUES ('李四', 25)

示例 5：
问题：把张三的年龄改成30
SQL：UPDATE users SET age = 30 WHERE name = '张三'

示例 6：
问题：删除所有已取消的订单
SQL：DELETE FROM orders WHERE status = 'cancelled'

示例 7：
问题：消费最高的用户是谁？
SQL：SELECT u.name, SUM(o.amount) as total FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.id, u.name ORDER BY total DESC LIMIT 1

示例 8：
问题：每个城市的用户数量
SQL：SELECT city, COUNT(*) as user_count FROM users GROUP BY city
"""


# ========== SQL 生成 ==========
def generate_sql(question: str) -> list:
    prompt = f"""
你是一个 MySQL 专家。根据用户的问题、数据库表结构和示例，生成对应的 SQL 语句。

数据库表结构：
{SCHEMA}

训练样本：
{EXAMPLES}

用户问题：{question}

要求：
1. 只返回 JSON 格式的 SQL 字符串数组，不要任何其他文字
2. 根据用户意图生成合适的 SQL（SELECT / INSERT / UPDATE / DELETE）
3. 多步操作时在数组中放多条 SQL
4. 务必使用正确的字段名和表名
5. 联表查询时使用 JOIN

返回格式示例：
["SELECT * FROM users"]
["INSERT INTO users (name, age) VALUES ('王五', 22)"]
["UPDATE users SET city = '上海' WHERE name = '张三'", "SELECT * FROM users WHERE name = '张三'"]
"""
    raw = call_llm(prompt).strip()
    raw = raw.replace('```json', '').replace('```', '').strip()
    sql_list = json.loads(raw)
    if isinstance(sql_list, str):
        return [sql_list]
    return sql_list


# ========== SQL 执行 ==========
def execute_sql(sql_list: list):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        last_results, last_columns = None, []
        has_write = False
        for s in sql_list:
            with conn.cursor() as cursor:
                cursor.execute(s)
                sql_type = s.strip().upper().split()[0]
                if sql_type == 'SELECT':
                    last_results = cursor.fetchall()
                    last_columns = [desc[0] for desc in cursor.description] if cursor.description else []
                else:
                    has_write = True
                    last_results = cursor.rowcount
                    last_columns = None
        if has_write:
            conn.commit()
        return last_results, last_columns, has_write
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ========== 结果润色 ==========
def polish_result(question: str, sql: str, results, columns: list) -> str:
    prompt = f"""
你是一个友好的数据助手。根据用户问题、执行的 SQL 和查询结果，用自然语言简洁回答。

用户问题：{question}
执行的 SQL：{sql}
列名：{columns}
查询结果：{results}

要求：
1. 200字以内，简洁自然
2. 不要解释 SQL 或技术细节
3. 直接告诉用户答案
"""
    return call_llm(prompt).strip()


# ========== 主流程 ==========
def nl2sql(question: str):
    if not question or not question.strip():
        print("❌ 问题不能为空")
        return None

    question = question.strip()
    print(f"📝 问题：{question}")

    # 1. 生成 SQL
    sql_list = generate_sql(question)
    print(f"🔧 SQL：{sql_list}")

    # 2. 执行 SQL
    try:
        result, columns, has_write = execute_sql(sql_list)
    except Exception as e:
        print(f"❌ 执行失败：{e}")
        return None

    # 3. 展示结果
    last_sql = sql_list[-1]
    sql_type = last_sql.strip().upper().split()[0]

    if sql_type == 'SELECT':
        print(f"✅ 查询结果：{result}")
        answer = polish_result(question, last_sql, result, columns)
        print(f"💬 回答：{answer}")
    else:
        op_names = {'INSERT': '插入', 'UPDATE': '更新', 'DELETE': '删除'}
        op_name = op_names.get(sql_type, '执行')
        print(f"✅ {op_name}成功，影响 {result} 行")
        print(f"💬 回答：已成功{op_name} {result} 行数据。")

    return result


# ========== 测试 ==========
if __name__ == '__main__':
    # 查询示例
    nl2sql("查询所有用户")
    print("\n" + "=" * 50 + "\n")

    # 联表查询示例
    nl2sql("北京的用户的订单总金额是多少？")
    print("\n" + "=" * 50 + "\n")

    # 聚合查询示例
    nl2sql("每个城市的用户数量")

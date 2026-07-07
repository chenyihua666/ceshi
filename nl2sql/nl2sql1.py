"""
NL2SQL V1：最简版本
功能：接收自然语言，生成 SQL，执行并返回结果
"""
import os
from openai import OpenAI
import pymysql
from dotenv import load_dotenv
load_dotenv()

# ========== LLM 配置 ==========
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen3.7-plus"
 # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models

def call_llm(prompt: str) -> str:
    """调用 LLM 并返回纯文本"""
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
    'database': os.getenv('DB_NAME', 'wolin_student_system'),
    'charset': 'utf8mb4'
}

# ========== 表结构描述 ==========
SCHEMA = """
数据库中有五张表：

1. students 表（学生信息）:
    -student_id: INT, 主键, 学生 ID
    -class_id: INT, 班级 ID（关联班级表）
    -name: VARCHAR(50), 学生姓名
    -hometown: VARCHAR(100), 生源地/家乡
    -graduate_school: VARCHAR(100), 毕业学校
    -major: VARCHAR(50), 专业
    -enrollment_date: DATE, 入学日期
    -graduation_date: DATE, 毕业日期
    -education: VARCHAR(20), 学历（如本科、硕士等）
    -consultant_id: INT, 顾问 ID（关联顾问表）
    -age: INT, 年龄
    -gender: CHAR(1), 性别（M/F）
    -is_delete: TINYINT(1), 逻辑删除标记（0-未删除，1-已删除）

2. class_info 表（班级信息）:
    -class_id: INT, 主键, 班级 ID
    -start_date: DATE, 开班日期/入学日期
    -head_teacher: VARCHAR(50), 班主任姓名
    -course_teacher: VARCHAR(50), 任课教师/课程教师

3. employment 表（就业/录用信息）:
    -id: INT, 主键, 记录 ID
    -student_id: INT, 外键，关联学生 ID
    -student_name: VARCHAR(50), 学生姓名（冗余字段）
    -class_id: INT, 外键，关联班级 ID
    -employment_open_date: DATE, 就业开放日期
    -offer_date: DATE, 获得录用通知的日期
    -company: VARCHAR(100), 录用公司名称
    -salary: DECIMAL(10,2), 薪资

4. scores 表（学生考试成绩记录）:
    -id: INT, 主键, 记录 ID
    -student_id: INT, 外键，关联学生 ID
    -exam_order: INT, 考试次序/批次
    -subject: VARCHAR(50), 考试科目（如数学、英语等）
    -score: DECIMAL(10,2), 考试成绩/分数

5. teachers 表（教师信息）:
    -teacher_id: INT, 主键, 教师 ID
    -name: VARCHAR(50), 教师姓名
    -managed_classes: VARCHAR(255), 管理的班级
    -contact: VARCHAR(100), 联系方式
    -title: VARCHAR(50), 职称/头衔
    -remark: TEXT, 备注
"""

# ========== 核心函数 ==========
def generate_sql(question: str) -> str:
    """
    用 LLM 把自然语言转成 SQL
    """
    prompt = f"""
你是一个 SQL 专家。根据用户的问题和数据库表结构，生成对应的 SQL 查询语句。

数据库表结构：
{SCHEMA}

用户问题：{question}

要求：
1. 只返回 SQL 语句，不要其他解释
2. 使用正确的字段名和表名
3. 如果涉及姓名查询，使用 name 字段
4. 查询家乡用 hometown 字段
"""
    sql = call_llm(prompt).strip()

    # 清理：去掉可能的 markdown 标记
    sql = sql.replace('```sql', '').replace('```', '').strip()

    return sql

def execute_sql(sql: str):
    """
    执行 SQL 并返回结果
    """
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            results = cursor.fetchall()
            return results
    except pymysql.err.ProgrammingError as e:
        print(f"❌ SQL 执行出错：{e}")
        print(f"💡 原因：AI 不知道表结构，猜错了字段名")
        return None
    finally:
        conn.close()

def nl2sql(question: str):
    """
    完整流程：自然语言 → SQL → 执行 → 返回结果
    """
    print(f"📝 用户问题：{question}")

    # Step 1: 生成 SQL
    sql = generate_sql(question)
    print(f"🔧 生成的 SQL：{sql}")

    # Step 2: 执行 SQL
    results = execute_sql(sql)
    if results is not None:
        print(f"✅ 查询结果：{results}")

    return results

# ========== 测试 ==========
if __name__ == '__main__':
    nl2sql("学生马龙的家乡在哪里？")
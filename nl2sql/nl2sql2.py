"""
NL2SQL V2：加上表结构描述
改进：把表结构注入 Prompt，让 AI 知道数据库长什么样
"""
import os
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

# ========== 新增：表结构描述 ==========
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
    -student_name: VARCHAR(50), 学生姓名（冗余字段，便于查询）
    -class_id: INT, 外键，关联班级 ID
    -employment_open_date: DATE, 就业开放日期（或开始求职日期）
    -offer_date: DATE, 获得录用通知（Offer）的日期
    -company: VARCHAR(100), 录用公司名称
    -salary: DECIMAL(10,2), 薪资（单位可依业务约定，如元/月）
4.scores 表（学生考试成绩记录）:
    -id: INT, 主键, 记录 ID
    -student_id: INT, 外键，关联学生 ID
    -exam_order: INT, 考试次序/批次（如第1次月考、第2次模拟考等）
    -subject: VARCHAR(50), 考试科目（如数学、英语等）
    -score: DECIMAL(10,2), 考试成绩/分数
5.teachers 表（教师信息）:
    -teacher_id: INT, 主键, 教师 ID
    -name: VARCHAR(50), 教师姓名
    -managed_classes: VARCHAR(255), 管理的班级（可存储班级ID列表或班级名称，通常为冗余/汇总字段）
    -contact: VARCHAR(100), 联系方式（电话/邮箱等）
    -title: VARCHAR(50), 职称/头衔（如教授、高级讲师等）
    -remark: TEXT, 备注/附加说明

关系：一个学生有多条成绩记录（一对多）
查询时需要用 student_id 关联两张表。
"""

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
3. 如果需要关联表，使用 JOIN
"""

    sql = call_llm(prompt).strip()
    sql = sql.replace('```sql', '').replace('```', '').strip()

    return sql

def execute_sql(sql: str):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            results = cursor.fetchall()
            return results
    finally:
        conn.close()

def nl2sql(question: str):
    print(f"📝 用户问题：{question}")

    sql = generate_sql(question)
    print(f"🔧 生成的 SQL：{sql}")

    try:
        results = execute_sql(sql)
        print(f"✅ 查询结果：{results}")
        return results
    except Exception as e:
        print(f"❌ 执行失败：{e}")
        return None

if __name__ == '__main__':
    nl2sql("所有学生的所有考试的平均分是多少")
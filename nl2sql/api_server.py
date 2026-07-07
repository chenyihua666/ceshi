"""
NL2SQL FastAPI 接口服务
整合 nl2sql1 / nl2sql2 / nl2sql4 三个版本，每个版本独立路由分组

启动方式：
    python api_server.py

接口文档：
    启动后访问 http://127.0.0.1:8000/docs
"""
import os
import json
import pymysql
from openai import OpenAI
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from contextlib import asynccontextmanager

# ========== 环境变量 ==========
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path, override=True)
load_dotenv(override=True)

# ========== LLM 配置（懒加载） ==========
MODEL = "qwen3.7-plus"
_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY 环境变量未设置，请检查 .env 文件")
        _client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DASH_SCOPE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
    return _client


def call_llm(prompt: str) -> str:
    completion = _get_client().chat.completions.create(
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
    -offer_date: DATE, 获得 Offer 的日期
    -company: VARCHAR(100), 录用公司名称
    -salary: DECIMAL(10,2), 薪资

4. scores 表（学生考试成绩记录）:
    -id: INT, 主键, 记录 ID
    -student_id: INT, 外键，关联学生 ID
    -exam_order: INT, 考试次序/批次
    -subject: VARCHAR(50), 考试科目
    -score: DECIMAL(10,2), 考试成绩/分数

5. teachers 表（教师信息）:
    -teacher_id: INT, 主键, 教师 ID
    -name: VARCHAR(50), 教师姓名
    -managed_classes: VARCHAR(255), 管理的班级
    -contact: VARCHAR(100), 联系方式
    -title: VARCHAR(50), 职称/头衔
    -remark: TEXT, 备注

关系：一个学生有多条成绩记录（一对多）
查询时需要用 student_id 关联两张表。
"""

EXAMPLES = """
示例 1：
问题：张三的数学成绩是多少？
SQL：SELECT s.score FROM students st JOIN scores s ON st.student_id = s.student_id WHERE st.name = '张三' AND s.subject = '数学'

示例 2：
问题：一班所有学生的数学成绩
SQL：SELECT st.name, s.score FROM students st JOIN scores s ON st.student_id = s.student_id JOIN class_info c ON st.class_id = c.class_id WHERE c.class_id = 1 AND s.subject = '数学'

示例 3：
问题：数学成绩最高的学生是谁？
SQL：SELECT st.name, s.score FROM students st JOIN scores s ON st.student_id = s.student_id WHERE s.subject = '数学' ORDER BY s.score DESC LIMIT 1

示例 4：
问题：每个学生的平均成绩
SQL：SELECT st.name, AVG(s.score) as avg_score FROM students st JOIN scores s ON st.student_id = s.student_id GROUP BY st.student_id, st.name
"""


def test_db_connection() -> bool:
    try:
        conn = pymysql.connect(**DB_CONFIG)
        conn.close()
        return True
    except Exception:
        return False


# ============================================================
#  nl2sql1 — V1 最简版本：单 SQL，只读查询
# ============================================================
def v1_generate_sql(question: str) -> str:
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
    sql = sql.replace('```sql', '').replace('```', '').strip()
    return sql


def v1_execute_sql(sql: str):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()


# ============================================================
#  nl2sql2 — V2 增加表关系 + JOIN 提示
# ============================================================
def v2_generate_sql(question: str) -> str:
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


def v2_execute_sql(sql: str):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()


# ============================================================
#  nl2sql4 — V4 完整增删改查 + Few-shot + 结果润色
# ============================================================
def v4_generate_sql(question: str) -> list:
    prompt = f"""
你是一个 MYSQL 专家。根据用户的问题、数据库表结构和示例，生成对应的 SQL 语句。

数据库表结构：
{SCHEMA}

示例：
{EXAMPLES}

用户问题：{question}

要求：
1. 只返回 JSON 格式的 SQL 字符串数组，不要其他解释
2. 根据意图生成合适的 SQL（SELECT 查询、INSERT 插入、UPDATE 更新、DELETE 删除）
3. 如果涉及多步操作，在数组中放多条 SQL
4. 使用正确的字段名和表名
5. 如果需要关联表，使用 JOIN

示例（返回 JSON 数组）：
["SELECT s.score FROM students st JOIN scores s ON st.student_id = s.student_id WHERE st.name = '张三' AND s.subject = '数学'"]

["INSERT INTO students (name, class_id, age, gender) VALUES ('思锦', 1, 20, 'F')", "INSERT INTO scores (student_id, subject, score, exam_order) VALUES (LAST_INSERT_ID(), '数学', 100.00, 1)"]
"""
    raw = call_llm(prompt).strip()
    raw = raw.replace('```json', '').replace('```', '').strip()
    sql_list = json.loads(raw)
    if isinstance(sql_list, str):
        return [sql_list]
    return sql_list


def v4_execute_sql(sql_list: list):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        last_results, last_columns = None, []
        has_non_select = False
        for s in sql_list:
            with conn.cursor() as cursor:
                cursor.execute(s)
                sql_type = s.strip().upper().split()[0]
                if sql_type == 'SELECT':
                    last_results = cursor.fetchall()
                    last_columns = [desc[0] for desc in cursor.description] if cursor.description else []
                else:
                    has_non_select = True
                    last_results = cursor.rowcount
                    last_columns = None
        if has_non_select:
            conn.commit()
        return last_results, last_columns, has_non_select
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def polish_result(question: str, sql: str, results, columns: list) -> str:
    prompt = f"""
你是一个友好的助手。根据用户的问题、执行的 SQL 和查询结果，尝试对结果进一步分析或总结。

用户问题：{question}
执行的 SQL：{sql}
列名：{columns}
查询结果：{results}

要求：
1. 500字以内简洁、自然的中文回答
2. 不要解释 SQL 或技术细节
3. 直接告诉用户答案
"""
    return call_llm(prompt).strip()


# ============================================================
#  Pydantic 模型
# ============================================================
class NL2SQLRequest(BaseModel):
    question: str = Field(..., description="自然语言问题", min_length=1, max_length=1000)

    class Config:
        json_schema_extra = {
            "example": {"question": "数学成绩最高和最低的学生是谁？"}
        }


class NL2SQLV4Request(BaseModel):
    question: str = Field(..., description="自然语言问题", min_length=1, max_length=1000)
    polish: bool = Field(default=True, description="是否对查询结果进行 AI 润色")
    dry_run: bool = Field(default=False, description="仅生成 SQL 不执行（调试用）")

    class Config:
        json_schema_extra = {
            "example": {
                "question": "数学成绩最高和最低的学生是谁？",
                "polish": True,
                "dry_run": False
            }
        }


class NL2SQLResponse(BaseModel):
    success: bool = Field(..., description="是否执行成功")
    question: str = Field(..., description="用户问题")
    sql: str = Field(..., description="生成的 SQL 语句")
    raw_result: Optional[Any] = Field(None, description="原始查询结果")
    answer: Optional[str] = Field(None, description="AI 润色后的自然语言回答")
    error: Optional[str] = Field(None, description="错误信息")


class NL2SQLV4Response(BaseModel):
    success: bool = Field(..., description="是否执行成功")
    question: str = Field(..., description="用户问题")
    sql_list: List[str] = Field(..., description="生成的 SQL 语句列表")
    sql_type: Optional[str] = Field(None, description="主要 SQL 类型: SELECT/INSERT/UPDATE/DELETE")
    raw_result: Optional[Any] = Field(None, description="原始查询结果")
    columns: Optional[List[str]] = Field(None, description="查询结果的列名")
    answer: Optional[str] = Field(None, description="AI 润色后的自然语言回答")
    affected_rows: Optional[int] = Field(None, description="影响行数（写操作时）")
    error: Optional[str] = Field(None, description="错误信息")


class HealthResponse(BaseModel):
    status: str = Field(..., description="服务状态")
    db_connected: bool = Field(..., description="数据库连接状态")
    model: str = Field(..., description="使用的 LLM 模型")


# ============================================================
#  FastAPI 应用
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_ok = test_db_connection()
    print(f"{'✅' if db_ok else '⚠️'} 数据库连接{'成功' if db_ok else '失败'}")
    print(f"🤖 LLM 模型: {MODEL}")
    print("🚀 NL2SQL API 服务已启动")
    yield
    print("👋 服务已关闭")


app = FastAPI(
    title="NL2SQL API",
    description="自然语言转 SQL 查询接口，包含 V1 / V2 / V4 三个版本",
    version="4.0.0",
    lifespan=lifespan,
)

# ── 公共接口 ──
@app.get("/", response_model=HealthResponse)
async def root():
    db_ok = test_db_connection()
    return HealthResponse(status="running", db_connected=db_ok, model=MODEL)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    db_ok = test_db_connection()
    return HealthResponse(
        status="healthy" if db_ok else "degraded",
        db_connected=db_ok,
        model=MODEL
    )


@app.get("/tables")
async def list_tables():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {"success": True, "tables": tables}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取表名失败: {str(e)}")


@app.get("/schema/{table_name}")
async def get_table_schema(table_name: str):
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = [
                {"field": row[0], "type": row[1], "null": row[2], "key": row[3], "default": row[4]}
                for row in cursor.fetchall()
            ]
        conn.close()
        return {"success": True, "table": table_name, "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取表结构失败: {str(e)}")


# ── V1 路由：最简版本，单SQL查询 ──
@app.post("/v1/nl2sql", response_model=NL2SQLResponse, tags=["V1-最简版本"])
async def v1_nl2sql(req: NL2SQLRequest):
    """
    **V1 最简版本**

    仅支持 SELECT 查询，适合简单的单表/联表查询。
    例：`"学生马龙的家乡在哪里？"`
    """
    question = req.question.strip()
    try:
        sql = v1_generate_sql(question)
        results = v1_execute_sql(sql)
        return NL2SQLResponse(
            success=True,
            question=question,
            sql=sql,
            raw_result=results,
        )
    except Exception as e:
        return NL2SQLResponse(
            success=False,
            question=question,
            sql="",
            error=str(e),
        )


# ── V2 路由：增加 JOIN 提示 ──
@app.post("/v2/nl2sql", response_model=NL2SQLResponse, tags=["V2-表关系版"])
async def v2_nl2sql(req: NL2SQLRequest):
    """
    **V2 表关系版**

    在 V1 基础上优化 Prompt，明确提示使用 JOIN，适合多表联查。
    例：`"所有学生的所有考试的平均分是多少"`
    """
    question = req.question.strip()
    try:
        sql = v2_generate_sql(question)
        results = v2_execute_sql(sql)
        return NL2SQLResponse(
            success=True,
            question=question,
            sql=sql,
            raw_result=results,
        )
    except Exception as e:
        return NL2SQLResponse(
            success=False,
            question=question,
            sql="",
            error=str(e),
        )


# ── V4 路由：完整增删改查 + 润色 ──
@app.post("/v4/nl2sql", response_model=NL2SQLV4Response, tags=["V4-完整版"])
async def v4_nl2sql(req: NL2SQLV4Request):
    """
    **V4 完整版**

    支持 SELECT / INSERT / UPDATE / DELETE 全部操作，带 Few-shot 示例和结果润色。
    例：`"数学成绩最高和最低的学生是谁？"`
    """
    question = req.question.strip()
    try:
        sql_list = v4_generate_sql(question)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL 生成失败: {str(e)}")

    if req.dry_run:
        return NL2SQLV4Response(
            success=True,
            question=question,
            sql_list=sql_list,
            answer="DRY RUN 模式：SQL 已生成但未执行",
        )

    try:
        result, columns, has_non_select = v4_execute_sql(sql_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL 执行失败: {str(e)}")

    last_sql = sql_list[-1]
    sql_type = last_sql.strip().upper().split()[0]

    if sql_type == 'SELECT':
        answer = polish_result(question, last_sql, result, columns) if req.polish else None
        return NL2SQLV4Response(
            success=True,
            question=question,
            sql_list=sql_list,
            sql_type="SELECT",
            raw_result=result,
            columns=columns,
            answer=answer,
        )
    else:
        op_names = {'INSERT': '插入', 'UPDATE': '更新', 'DELETE': '删除'}
        op_name = op_names.get(sql_type, '执行')
        return NL2SQLV4Response(
            success=True,
            question=question,
            sql_list=sql_list,
            sql_type=sql_type,
            affected_rows=result,
            answer=f"已成功{op_name} {result} 行数据。",
        )


# ============================================================
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

from google.adk.agents import Agent, SequentialAgent
from .tools import compare_docs, get_product_number, determine_hold, update_hold_database_before_tool_callback, update_hold_database


database_update_agent = Agent(
    name="DatabaseUpdateAgent",
    description="Updates a database to put a product on hold ",
    model="gemini-2.5-flash",
    instruction=(
        "You are an intelligent assistant capable of updating a database containt product hold status information "
        "Use the `update_hold_database` tool to update the product hold database.  "
    ),
    tools=[update_hold_database],
    before_tool_callback=[update_hold_database_before_tool_callback]
)

hold_agent = Agent(
    name="ProductHoldAgent",
    description="Reviews a COA analysis to determine product hold status",
    model="gemini-2.5-flash",
    instruction=(
        "You are an intelligent assistant capable of reviewing a COA analysis to determine whether or not a product should go on hold."
        "Use the `determine_hold` tool to determine the product hold status."
    ),
    tools=[determine_hold]
)

hold_pipeline_agent = SequentialAgent(
    name="HoldPipelineAgent",
    sub_agents=[hold_agent, database_update_agent],
    description="Executes a sequence of determining hold status, updating hold database.",
)

root_agent = Agent(
    name="COAAnalysisAgent",
    model="gemini-2.5-flash",
    instruction=(
        "You are an intelligent assistant with the ability to compare PDF documents "
        "stored in Google Cloud Storage. When a user provides a GCS URI (a path starting with 'gs://'), "
        "First, use the `get_product_number` tool to extract the product number."
        "Second, provide the GCS URI and { product? } to the `compare_docs` tool. Present the analysis to the user before moving on to the next step." 
        "Third, use the `HoldPipelineAgent` to execute the product hold pipeline. "
    ),
    tools=[
        get_product_number, compare_docs
    ],
    sub_agents=[hold_pipeline_agent]
)

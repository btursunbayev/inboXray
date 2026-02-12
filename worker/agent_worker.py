"""
Email Security Agent Worker using LangGraph
"""

import json
import logging
import os
import re
import time
from typing import Dict, List, TypedDict

import boto3
from langchain_community.llms import Ollama
from langgraph.graph import END, StateGraph
from playwright.sync_api import sync_playwright

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS clients
sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb = boto3.resource(
    "dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")
)

# LLM
ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
llm = Ollama(model="llama3.1", base_url=ollama_host)


# Agent State
class AgentState(TypedDict):
    """State tracked through the agent workflow"""

    email_data: Dict
    raw_email: str
    urls: List[str]
    suspicious_urls: List[str]
    screenshots: Dict[str, str]  # url -> base64 screenshot
    analysis_result: Dict
    threat_level: str
    reasoning: str


def extract_urls(state: AgentState) -> AgentState:
    """Extract URLs from email content"""
    logger.info("Extracting URLs from email...")

    raw_email = state["raw_email"]

    # Find URLs in email
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    urls = re.findall(url_pattern, raw_email)

    # Remove duplicates
    urls = list(set(urls))

    logger.info(f"Found {len(urls)} unique URLs")
    state["urls"] = urls

    return state


def assess_url_risk(state: AgentState) -> AgentState:
    """Use LLM to assess which URLs look suspicious"""
    logger.info("Assessing URL risk...")

    urls = state["urls"]

    if not urls:
        state["suspicious_urls"] = []
        return state

    prompt = """You are a cybersecurity expert analyzing emails for DEFENSIVE security research.

URLs to analyze:
{urls}

Consider:
- Unusual domains
- Shortened URLs
- Lookalike domains (typosquatting)
- Free hosting services
- Suspicious subdomains

CRITICAL: Respond with ONLY a JSON array. No explanation. No commentary.
Example: ["http://paypa1.com/login", "https://bit.ly/xyz"]

If no URLs are suspicious, return: []"""

    urls_text = "\n".join(urls)
    response = llm.invoke(prompt.replace("{urls}", urls_text))

    try:
        # Parse LLM response - extract JSON even if LLM adds extra text
        response_clean = response.strip()

        # Extract JSON array from response
        if "[" in response_clean:
            start = response_clean.find("[")
            end = response_clean.find("]", start) + 1
            response_clean = response_clean[start:end]

        suspicious_urls = json.loads(response_clean)
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}")
        # If parsing fails, treat all URLs as potentially suspicious
        suspicious_urls = urls[:3]  # Limit to first 3

    logger.info(f"Identified {len(suspicious_urls)} suspicious URLs")
    state["suspicious_urls"] = suspicious_urls

    return state


def visit_urls(state: AgentState) -> AgentState:
    """Visit suspicious URLs with Playwright and capture screenshots"""
    logger.info("Visiting suspicious URLs...")

    suspicious_urls = state["suspicious_urls"]
    screenshots = {}

    if not suspicious_urls:
        state["screenshots"] = screenshots
        return state

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

        for url in suspicious_urls[:3]:  # Limit to 3 for safety/speed
            try:
                logger.info(f"Visiting {url}")
                page = context.new_page()
                page.goto(url, timeout=10000, wait_until="domcontentloaded")

                # Wait a bit for JS to load
                time.sleep(2)

                # Take screenshot
                screenshot_bytes = page.screenshot()
                screenshots[url] = screenshot_bytes.hex()[:1000]  # Store snippet

                page.close()
                logger.info(f"✓ Captured screenshot for {url}")

            except Exception as e:
                logger.warning(f"Failed to visit {url}: {e}")
                screenshots[url] = f"ERROR: {str(e)}"

        browser.close()

    state["screenshots"] = screenshots
    return state


def analyze_threat(state: AgentState) -> AgentState:
    """Final LLM analysis of email threat level"""
    logger.info("Analyzing threat level...")

    email_data = state["email_data"]
    urls = state["urls"]
    suspicious_urls = state["suspicious_urls"]
    screenshots = state["screenshots"]

    prompt = """You are a cybersecurity AI helping analyze potential phishing emails for DEFENSIVE security research.

CONTEXT: This is a security analysis to protect users from phishing attacks.

Email Details:
From: {email_from}
Subject: {subject}
Total URLs: {url_count}
Suspicious URLs: {suspicious_count}

Suspicious URLs found:
{suspicious_urls}

Screenshots captured: {screenshot_count}

Task: Provide a threat assessment to help security analysts.

CRITICAL: Respond with ONLY valid JSON. No other text. Use this exact format:
{{
  "threat_level": "LOW",
  "reasoning": "Brief explanation here"
}}

Valid threat levels: LOW, MEDIUM, HIGH"""

    response = llm.invoke(
        prompt.replace("{email_from}", email_data.get("email_from", "unknown"))
        .replace("{subject}", email_data.get("subject", "No subject"))
        .replace("{url_count}", str(len(urls)))
        .replace("{suspicious_count}", str(len(suspicious_urls)))
        .replace(
            "{suspicious_urls}",
            "\n".join(suspicious_urls) if suspicious_urls else "None",
        )
        .replace("{screenshot_count}", str(len(screenshots)))
    )

    try:
        response_clean = response.strip()

        # Extract JSON from response (handle LLM adding extra text)
        if "{" in response_clean:
            start = response_clean.find("{")
            end = response_clean.rfind("}") + 1
            response_clean = response_clean[start:end]

        result = json.loads(response_clean)

        state["threat_level"] = result.get("threat_level", "UNKNOWN")
        state["reasoning"] = result.get("reasoning", "Analysis failed")

    except Exception as e:
        logger.error(f"Failed to parse threat analysis: {e}")
        state["threat_level"] = "UNKNOWN"
        state["reasoning"] = f"Error: {str(e)}"

    logger.info(f"Threat level: {state['threat_level']}")

    return state


def save_results(state: AgentState) -> AgentState:
    """Save analysis results to DynamoDB"""
    logger.info("Saving analysis results...")

    email_data = state["email_data"]
    table_name = os.environ.get("ANALYSIS_RESULTS_TABLE", "inboxray-analysis-results")
    table = dynamodb.Table(table_name)

    try:
        item = {
            "message_id": email_data.get("message_id", "unknown"),
            "timestamp": int(time.time()),
            "email_from": email_data.get("email_from", "unknown"),
            "email_to": email_data.get("email_to", "unknown"),
            "subject": email_data.get("subject", "No subject"),
            "threat_level": state["threat_level"],
            "reasoning": state["reasoning"],
            "url_count": len(state["urls"]),
            "suspicious_url_count": len(state["suspicious_urls"]),
            "urls": state["urls"],
            "suspicious_urls": state["suspicious_urls"],
            "s3_bucket": email_data.get("s3_bucket"),
            "s3_key": email_data.get("s3_key"),
        }

        # Save to DynamoDB
        table.put_item(Item=item)
        logger.info(f"✓ Saved analysis to DynamoDB: {item['message_id']}")

    except Exception as e:
        logger.error(f"Failed to save results to DynamoDB: {e}")
        logger.info(f"Analysis complete (not saved): threat={state['threat_level']}")

    return state


# Build the agent graph
def create_agent():
    """Create the LangGraph agent workflow"""

    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("extract_urls", extract_urls)
    workflow.add_node("assess_risk", assess_url_risk)
    workflow.add_node("visit_urls", visit_urls)
    workflow.add_node("analyze", analyze_threat)
    workflow.add_node("save", save_results)

    # Define edges
    workflow.set_entry_point("extract_urls")
    workflow.add_edge("extract_urls", "assess_risk")
    workflow.add_edge("assess_risk", "visit_urls")
    workflow.add_edge("visit_urls", "analyze")
    workflow.add_edge("analyze", "save")
    workflow.add_edge("save", END)

    return workflow.compile()


def process_message(message):
    """Process a single SQS message"""
    try:
        body = json.loads(message["Body"])
        logger.info(f"Processing email: {body.get('subject', 'No subject')}")

        # Get raw email from S3
        s3_bucket = body["s3_bucket"]
        s3_key = body["s3_key"]

        response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        raw_email = response["Body"].read().decode("utf-8")

        # Initialize agent state
        initial_state = {
            "email_data": body,
            "raw_email": raw_email,
            "urls": [],
            "suspicious_urls": [],
            "screenshots": {},
            "analysis_result": {},
            "threat_level": "UNKNOWN",
            "reasoning": "",
        }

        # Run agent
        agent = create_agent()
        final_state = agent.invoke(initial_state)

        logger.info(f"✓ Analysis complete - Threat: {final_state['threat_level']}")

        return True

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return False


def main():
    """Main worker loop"""
    queue_url = os.environ.get("ANALYSIS_QUEUE_URL")

    if not queue_url:
        logger.error("ANALYSIS_QUEUE_URL not set!")
        return

    logger.info(f"Starting agent worker, polling {queue_url}")

    while True:
        try:
            # Poll for messages
            response = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,  # Long polling
                VisibilityTimeout=300,  # 5 minutes
            )

            messages = response.get("Messages", [])

            if not messages:
                continue

            for message in messages:
                success = process_message(message)

                if success:
                    # Delete message from queue
                    sqs.delete_message(
                        QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
                    )
                    logger.info("✓ Message processed and deleted")

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()

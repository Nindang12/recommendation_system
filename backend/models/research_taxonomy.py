from __future__ import annotations

from typing import Dict, List


RESEARCH_DIRECTIONS: List[Dict[str, str]] = [
    {"value": "artificial-intelligence", "label": "Tri tue nhan tao"},
    {"value": "data-science-knowledge-graph", "label": "Khoa hoc du lieu va Knowledge Graph"},
    {"value": "computer-vision-multimedia", "label": "Thi giac may tinh va da phuong tien"},
    {"value": "natural-language-processing", "label": "Xu ly ngon ngu tu nhien"},
    {"value": "iot-smart-systems", "label": "IoT va he thong thong minh"},
    {"value": "smart-manufacturing-industry-4", "label": "San xuat thong minh va cong nghiep 4.0"},
    {"value": "healthcare-biomedicine", "label": "Y te so va cong nghe sinh hoc"},
    {"value": "energy-environment", "label": "Nang luong va moi truong"},
    {"value": "cybersecurity-trust", "label": "An toan thong tin va he thong tin cay"},
    {"value": "robotics-autonomous-systems", "label": "Robotics va he thong tu hanh"},
]


RESEARCH_TOPICS: List[Dict[str, str]] = [
    {
        "value": "machine-learning",
        "label": "Machine Learning",
        "direction": "artificial-intelligence",
    },
    {
        "value": "deep-learning",
        "label": "Deep Learning",
        "direction": "artificial-intelligence",
    },
    {
        "value": "reinforcement-learning",
        "label": "Reinforcement Learning",
        "direction": "artificial-intelligence",
    },
    {
        "value": "explainable-ai",
        "label": "Explainable AI",
        "direction": "artificial-intelligence",
    },
    {
        "value": "data-science",
        "label": "Khoa hoc du lieu",
        "direction": "data-science-knowledge-graph",
    },
    {
        "value": "knowledge-graph",
        "label": "Knowledge Graph",
        "direction": "data-science-knowledge-graph",
    },
    {
        "value": "graph-neural-networks",
        "label": "Graph Neural Networks",
        "direction": "data-science-knowledge-graph",
    },
    {
        "value": "big-data-analytics",
        "label": "Phan tich du lieu lon",
        "direction": "data-science-knowledge-graph",
    },
    {
        "value": "computer-vision",
        "label": "Computer Vision",
        "direction": "computer-vision-multimedia",
    },
    {
        "value": "medical-imaging",
        "label": "Anh y te",
        "direction": "computer-vision-multimedia",
    },
    {
        "value": "image-processing",
        "label": "Xu ly anh",
        "direction": "computer-vision-multimedia",
    },
    {
        "value": "video-analytics",
        "label": "Phan tich video",
        "direction": "computer-vision-multimedia",
    },
    {
        "value": "natural-language-processing",
        "label": "Xu ly ngon ngu tu nhien",
        "direction": "natural-language-processing",
    },
    {
        "value": "information-retrieval",
        "label": "Truy xuat thong tin",
        "direction": "natural-language-processing",
    },
    {
        "value": "large-language-models",
        "label": "Mo hinh ngon ngu lon",
        "direction": "natural-language-processing",
    },
    {
        "value": "ai-healthcare",
        "label": "AI trong y te",
        "direction": "healthcare-biomedicine",
    },
    {
        "value": "bioinformatics",
        "label": "Tin sinh hoc",
        "direction": "healthcare-biomedicine",
    },
    {
        "value": "digital-health",
        "label": "Y te so",
        "direction": "healthcare-biomedicine",
    },
    {
        "value": "iot",
        "label": "Internet of Things",
        "direction": "iot-smart-systems",
    },
    {
        "value": "smart-city",
        "label": "Do thi thong minh",
        "direction": "iot-smart-systems",
    },
    {
        "value": "edge-computing",
        "label": "Tinh toan bien",
        "direction": "iot-smart-systems",
    },
    {
        "value": "smart-manufacturing",
        "label": "San xuat thong minh",
        "direction": "smart-manufacturing-industry-4",
    },
    {
        "value": "predictive-maintenance",
        "label": "Bao tri du doan",
        "direction": "smart-manufacturing-industry-4",
    },
    {
        "value": "digital-twin",
        "label": "Digital Twin",
        "direction": "smart-manufacturing-industry-4",
    },
    {
        "value": "renewable-energy",
        "label": "Nang luong tai tao",
        "direction": "energy-environment",
    },
    {
        "value": "smart-grid",
        "label": "Luoi dien thong minh",
        "direction": "energy-environment",
    },
    {
        "value": "environmental-monitoring",
        "label": "Giam sat moi truong",
        "direction": "energy-environment",
    },
    {
        "value": "cybersecurity",
        "label": "An toan thong tin",
        "direction": "cybersecurity-trust",
    },
    {
        "value": "privacy-preserving-ai",
        "label": "AI bao ve rieng tu",
        "direction": "cybersecurity-trust",
    },
    {
        "value": "blockchain-security",
        "label": "Bao mat Blockchain",
        "direction": "cybersecurity-trust",
    },
    {
        "value": "robotics",
        "label": "Robotics",
        "direction": "robotics-autonomous-systems",
    },
    {
        "value": "autonomous-systems",
        "label": "He thong tu hanh",
        "direction": "robotics-autonomous-systems",
    },
]


ALLOWED_RESEARCH_TOPICS = {topic["value"] for topic in RESEARCH_TOPICS}
RESEARCH_TOPIC_DIRECTION_MAP = {topic["value"]: topic["direction"] for topic in RESEARCH_TOPICS}
RESEARCH_DIRECTION_LABEL_MAP = {direction["value"]: direction["label"] for direction in RESEARCH_DIRECTIONS}
RESEARCH_TOPIC_LABEL_MAP = {topic["value"]: topic["label"] for topic in RESEARCH_TOPICS}


def research_topic_direction(topic_value: str) -> str | None:
    return RESEARCH_TOPIC_DIRECTION_MAP.get(topic_value)


def research_direction_label(direction_value: str | None) -> str | None:
    if not direction_value:
        return None
    return RESEARCH_DIRECTION_LABEL_MAP.get(direction_value, direction_value)

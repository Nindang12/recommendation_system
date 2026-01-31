from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "rd_recommendation_system")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

print(f"Connected to MongoDB database: {DB_NAME}")

# =========================
# 1. Insert ResearchField
# =========================

research_fields = [
    {
        "field_id": "AI_001",
        "label": "Trí tuệ nhân tạo",
        "description": "Nghiên cứu về các phương pháp và hệ thống thông minh.",
        "hierarchy": {
            "parent_id": None,
            "level": 1
        },
        "mapping": {
            "standard": "ACM",
            "standard_code": "I.2.0"
        }
    },
    {
        "field_id": "AI_002",
        "label": "Thị giác máy tính",
        "description": "Xử lý và phân tích ảnh và video.",
        "hierarchy": {
            "parent_id": "AI_001",
            "level": 2
        },
        "mapping": {
            "standard": "FoS",
            "standard_code": "1.2.3"
        }
    }
]

if db.research_fields.count_documents({}) == 0:
    db.research_fields.insert_many(research_fields)
    print("Inserted research_fields")

# =========================
# 2. Insert Industry
# =========================

industries = [
    {
        "industry_id": "MED_DEV",
        "industry_name": "Thiết bị y tế",
        "standard_mapping": {
            "type": "NAICS",
            "code": "339112"  # Surgical and Medical Instrument Manufacturing
        },
        "related_sectors": ["Chăm sóc sức khỏe", "Công nghệ y sinh"]
    }
]

if db.industries.count_documents({}) == 0:
    db.industries.insert_many(industries)
    print("Inserted industries")

# =========================
# 3. Insert MethodTechnique
# =========================

method_techniques = [
    {
        "tech_id": "TECH_CNN",
        "name": "Convolutional Neural Network",
        "standard_ref": "ISO/IEC 22989",
        "category": "Học sâu",
        "related_fields": ["AI_001", "AI_002"]
    },
    {
        "tech_id": "TECH_PACS",
        "name": "PACS integration",
        "standard_ref": "DICOM integration best practices",
        "category": "Hệ thống y tế",
        "related_fields": ["AI_002"]
    }
]

if db.method_techniques.count_documents({}) == 0:
    db.method_techniques.insert_many(method_techniques)
    print("Inserted method_techniques")

# =========================
# 4. Insert OutputAsset
# =========================

output_assets = [
    {
        "asset_id": "OUT_0001",
        "title": "AI hỗ trợ chẩn đoán X-quang - Bài báo hội nghị",
        "type": "Bài báo",
        "metadata": {
            "publisher": "Hội nghị Khoa học ABC",
            "year": 2025,
            "status": "published"
        },
        "links": {
            "produced_by_project": "PRJ_0001",
            "commercialized_by": None
        }
    }
]

if db.output_assets.count_documents({}) == 0:
    db.output_assets.insert_many(output_assets)
    print("Inserted output_assets")

# =========================
# 5. Insert Experts
# =========================

experts = [
    {
        "expert_id": "EXP_0001",
        "basic_info": {
            "name": "TS. Nguyễn Văn A",
            "birth_year": 1985,
            "gender": "male",
            "location": "VN-HCM",
            "nationality": "VN",
            "preferred_language": "vi"
        },
        "identifiers": {
            "ORCID": "0000-0001-2345-6789",
            "ScopusID": "123456789",
            "ResearcherID": "A-1234-2020"
        },
        "contact_info": {
            "phone": "+84-912345678",
            "email": "nguyenvana@example.edu.vn",
            "preferred_contact_method": "email",
            "social_links": {
                "LinkedIn": "https://www.linkedin.com/in/nguyenvana",
                "ResearchGate": "https://www.researchgate.net/profile/Nguyen-A",
                "GoogleScholar": "https://scholar.google.com/citations?user=XXXXX"
            }
        },
        "academic_profile": {
            "academic_rank": "TS",
            "degrees": ["Cử nhân CNTT", "Thạc sĩ Khoa học máy tính", "Tiến sĩ Trí tuệ nhân tạo"],
            "academic_status": "Giảng viên",
            "current_affiliation": {
                "org_name": "Trường Đại học ABC",
                "type": "Trường đại học",
                "department": "Khoa Công nghệ thông tin",
                "position_title": "Giảng viên chính"
            },
            "affiliation_history": [
                {
                    "org": "Trường Đại học ABC",
                    "role": "Giảng viên",
                    "duration": "2015-01-01/2025-01-01"
                }
            ],
            "teaching_experience": "10 năm giảng dạy các môn liên quan đến AI và Thị giác máy tính."
        },
        "research_capacity": {
            "research_fields": ["AI_002"],
            "research_interests": ["computer vision", "medical imaging"],
            "skills_methods": [
                {"name": "CNN", "proficiency_level": "advanced"},
                {"name": "PACS integration", "proficiency_level": "intermediate"}
            ],
            "applied_industries": ["MED_DEV"],
            "academic_metrics": {
                "publication_count": 30,
                "h_index": 22,
                "citation_count": 1500,
                "i10_index": 18,
                "altmetrics": 50
            }
        },
        "activities_and_outputs": {
            "list_outputs": [
                {
                    "type": "Bài báo",
                    "title": "Deep CNN for Chest X-ray Disease Classification",
                    "year": 2024,
                    "doi_id": "10.1234/abc.2024.001",
                    "publisher": "Journal of Medical Imaging"
                }
            ],
            "collaborators": [
                {
                    "name": "TS. Trần Văn B",
                    "affiliation": "Trường Đại học XYZ",
                    "relation_type": "Đồng tác giả",
                    "duration": "2020-01-01/2024-12-31"
                }
            ],
            "grant_history": [
                {
                    "grant_id": "GRANT_0001",
                    "funder_name": "Quỹ NAFOSTED",
                    "amount": 1500000000,
                    "year": 2023,
                    "linked_project": "PRJ_0001"
                }
            ],
            "projects_participation": [
                {
                    "project_id": "PRJ_0001",
                    "title": "AI hỗ trợ chẩn đoán X-quang",
                    "role": "PI",
                    "duration": "2025-01-01/2026-12-31",
                    "status": "ongoing"
                }
            ]
        },
        "governance": {
            "privacy": {
                "privacy_level": "Internal",
                "field_privacy": {
                    "email": "Internal",
                    "outputs": "Public"
                },
                "consent": {
                    "status": "accepted",
                    "date": "2025-01-01"
                }
            },
            "temporal_freshness": {
                "last_update": "2025-01-15",
                "update_source": "manual"
            }
        }
    }
]

if db.experts.count_documents({}) == 0:
    db.experts.insert_many(experts)
    print("Inserted experts")

# =========================
# 6. Insert Enterprises
# =========================

enterprises = [
    {
        "enterprise_id": "ENT_0001",
        "basic_info": {
            "name": "Công ty MedTech X",
            "tax_code": "0312345678",
            "founded_year": 2015,
            "industry_codes": ["339112"],
            "location": "VN-HCM",
            "organization_metrics": {
                "size": "SME",
                "income": 50000000000,
                "employees": 120,
                "certifications": ["ISO 13485", "ISO 9001"]
            }
        },
        "representatives": {
            "legal_rep": {
                "name": "Nguyễn Văn C",
                "position": "Tổng giám đốc"
            },
            "rd_contact": {
                "expert_id": "EXP_0001",
                "name": "TS. Nguyễn Văn A",
                "email": "rnd@medtechx.vn",
                "phone": "+84-901234567"
            }
        },
        "rd_profile": {
            "rd_focus_fields": ["AI_002"],
            "technology_needs": [
                {
                    "need": "Chẩn đoán hình ảnh X-quang bằng AI",
                    "desired_TRL": 7
                }
            ],
            "rd_capacity": {
                "research_staff": 15,
                "labs": ["Phòng R&D thiết bị chẩn đoán hình ảnh"],
                "equipment": ["Máy X-quang số", "Máy chủ GPU"]
            },
            "investment_and_metrics": {
                "innovation_index": 0.8,
                "investment_history": [
                    {
                        "source": "Ngân sách nội bộ",
                        "amount": 8000000000,
                        "purpose": "Phát triển hệ thống AI hỗ trợ chẩn đoán"
                    }
                ],
                "sustainability_metrics": "Tuân thủ tiêu chuẩn môi trường và y tế hiện hành.",
                "risk_profile": "Chấp nhận rủi ro trung bình cho các dự án AI y tế."
            }
        },
        "outputs_and_transfers": {
            "commercialized_assets": [
                {
                    "product": "Hệ thống lưu trữ và truyền tải hình ảnh y tế (PACS)",
                    "year": 2022,
                    "revenue_estimate": 12000000000
                }
            ],
            "patents_outputs": [
                {
                    "type": "Bằng sáng chế",
                    "patent_id": "VN-123456",
                    "status": "granted"
                }
            ],
            "transfer_history": [
                {
                    "mode": "Licensing",
                    "year": 2023,
                    "partner": "Bệnh viện Đa khoa ABC"
                }
            ]
        },
        "relations": {
            "rd_projects": [
                {
                    "project_id": "PRJ_0001",
                    "role": "industry partner",
                    "status": "ongoing"
                }
            ],
            "partnerships_history": [
                {
                    "partner_name": "Bệnh viện Đa khoa ABC",
                    "role": "Triển khai thử nghiệm hệ thống",
                    "duration": "2022-01-01/2024-12-31"
                }
            ],
            "funder_relations": [
                {
                    "funder_id": "FUN_0001",
                    "year": 2023,
                    "amount": 2000000000
                }
            ]
        },
        "governance": {
            "privacy": {
                "privacy_level": "Internal",
                "field_privacy": {
                    "income": "Restricted",
                    "rd_contact": "Internal"
                },
                "anonymization_rules": "Ẩn doanh thu chi tiết theo từng hợp đồng.",
                "consent": {
                    "status": "accepted",
                    "date": "2024-12-31"
                }
            },
            "temporal_freshness": {
                "last_update": "2025-01-10",
                "update_source": "internal_system",
                "freshness_score": 0.9
            }
        }
    }
]

if db.enterprises.count_documents({}) == 0:
    db.enterprises.insert_many(enterprises)
    print("Inserted enterprises")

# =========================
# 7. Insert Funders
# =========================

funders = [
    {
        "funder_id": "FUN_0001",
        "basic_info": {
            "name": "Quỹ NAFOSTED",
            "type": "Government",
            "location": "VN-HN",
            "budget_capacity": 3000000000
        },
        "representatives": {
            "name": "Trần Thị D",
            "position": "Giám đốc chương trình",
            "email": "nafosted@example.gov.vn"
        },
        "funding_strategy": {
            "funding_domains": ["AI_002"],
            "trl_range_focus": "4-7",
            "eligibility_criteria": "Tổ chức nghiên cứu, trường đại học tại Việt Nam",
            "typical_grant_size": 2000000000
        },
        "programs": [
            {
                "program_id": "PRG_2025_AI_HEALTH",
                "title": "Chương trình AI trong y sinh 2025",
                "application_window": "2025-03-01/2025-06-30",
                "max_budget": 3000000000,
                "evaluation_criteria": "Chất lượng khoa học, tác động, tính khả thi.",
                "funding_type": "grant",
                "application_process": "Nộp hồ sơ trực tuyến, phản biện kín, xét duyệt hội đồng.",
                "reporting_requirements": "Báo cáo giữa kỳ và cuối kỳ, sản phẩm khoa học."
            }
        ],
        "funding_history": {
            "funded_projects": [
                {
                    "project_id": "PRJ_0001",
                    "title": "AI hỗ trợ chẩn đoán X-quang",
                    "domain": "AI_002",
                    "grant_amount": 2500000000,
                    "year": 2025,
                    "status": "ongoing"
                }
            ],
            "annual_grant_history": [
                {
                    "year": 2024,
                    "total_amount": 100000000000,
                    "recipients": ["Trường Đại học ABC", "Viện Nghiên cứu XYZ"]
                }
            ],
            "success_stories": [
                "Dự án AI phân tích ảnh MRI đạt giải thưởng quốc gia."
            ]
        },
        "impact_metrics": {
            "projects_success_rate": 0.75,
            "patents_generated": 45,
            "commercialization_rate": 0.3
        },
        "relations": {
            "funds_projects": ["PRJ_0001"],
            "calls_for_programs": ["PRG_2025_AI_HEALTH"],
            "supports_fields": ["AI_001", "AI_002"],
            "invests_in": ["ENT_0001"],
            "collaborates_with": []
        },
        "governance": {
            "privacy": {
                "privacy_level": "Internal",
                "field_privacy": {
                    "grant_amount": "Restricted",
                    "representative_email": "Internal"
                },
                "anonymization_rules": "Ẩn danh thông tin chi tiết về cá nhân nhận tài trợ.",
                "consent": {
                    "status": "accepted",
                    "date": "2024-12-31"
                }
            },
            "temporal_freshness": {
                "last_update": "2025-01-05",
                "update_source": "official_website",
                "freshness_score": 0.95
            }
        }
    }
]

if db.funders.count_documents({}) == 0:
    db.funders.insert_many(funders)
    print("Inserted funders")

# =========================
# 8. Insert Projects
# =========================

projects = [
    {
        "project_id": "PRJ_0001",
        "basic_info": {
            "title": "AI hỗ trợ chẩn đoán X-quang",
            "description": "Ứng dụng AI trong phân tích ảnh X-quang.",
            "research_domain": "AI_002",
            "keywords": ["AI", "X-ray", "computer vision"],
            "location": "VN-HCM",
            "status": "ongoing"
        },
        "requirements_and_timeline": {
            "required_skills": ["CNN", "PACS integration"],
            "technology_readiness_level": 5,
            "budget": 2500000000,
            "funding_source": "FUN_0001",
            "timeline": {
                "start_date": "2025-01-01",
                "end_date": "2026-12-31"
            }
        },
        "rd_profile": {
            "outputs": [
                {
                    "type": "Bài báo",
                    "title": "Deep CNN for Chest X-ray Disease Classification",
                    "year": 2024,
                    "id": "10.1234/abc.2024.001"
                }
            ],
            "trl_progression": [
                {
                    "year": 2024,
                    "trl_level": 4
                },
                {
                    "year": 2025,
                    "trl_level": 5
                }
            ],
            "technology_gap": {
                "current_trl": 5,
                "target_trl": 7,
                "gap_description": "Cần mở rộng thử nghiệm lâm sàng và tích hợp với hệ thống PACS bệnh viện."
            },
            "impact_and_sustainability": {
                "impact_metrics": {
                    "papers_count": 1,
                    "patents_count": 0,
                    "commercialization_revenue": 0
                },
                "sustainability_metrics": "Kỳ vọng giảm tải cho bác sĩ và nâng cao chất lượng chẩn đoán."
            }
        },
        "relations": {
            "participants": [
                {
                    "expert_id": "EXP_0001",
                    "role": "PI",
                    "period": "2025-01-01/2026-12-31"
                }
            ],
            "enterprise_partners": [
                {
                    "enterprise_id": "ENT_0001",
                    "type": "industry partner"
                }
            ],
            "funders": [
                {
                    "funder_id": "FUN_0001",
                    "grant_period": "2025-2026",
                    "grant_amount": 2500000000
                }
            ],
            "related_projects": []
        },
        "follow_up_opportunities": {
            "next_phase_project": "PRJ_0002",
            "spin_off_potential": "Có tiềm năng thành lập startup về AI chẩn đoán hình ảnh.",
            "scale_up_plan": "Triển khai thử nghiệm tại 3 bệnh viện lớn, sau đó thương mại hóa toàn quốc."
        },
        "governance": {
            "privacy": {
                "privacy_level": "Internal",
                "field_privacy": {
                    "budget": "Restricted",
                    "outputs": "Public"
                },
                "consent": {
                    "status": "accepted",
                    "date": "2025-01-01"
                }
            },
            "temporal_freshness": {
                "last_update": "2025-01-20",
                "update_source": "project_management_system",
                "freshness_score": 0.9
            }
        }
    }
]

if db.projects.count_documents({}) == 0:
    db.projects.insert_many(projects)
    print("Inserted projects")

print("\nSeed data inserted successfully.")


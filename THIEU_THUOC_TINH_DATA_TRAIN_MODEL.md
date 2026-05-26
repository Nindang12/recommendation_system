# Thuoc tinh con thieu de phuc vu train model

File nay tom tat cac thuoc tinh quan trong con thieu trong bo JSONL moi, doi chieu voi schema/dinh huong du lieu trong `add_data`.

## Expert

Can bo sung cac truong sau:

- `research_capacity.research_directions`: de tao quan he `Expert -[:RESEARCHES]-> ResearchDirection`.
- `research_capacity.research_topics`: de match chuyen mon expert voi topic cua project.
- `research_capacity.skills_methods`: de tao quan he `Expert -[:HAS_SKILL]-> Skill`.
- `research_capacity.applied_industries`: de biet expert co kinh nghiem ung dung trong nganh nao.
- `activities_and_outputs.projects_participation`: de tao positive pairs `Expert -[:PARTICIPATES_IN]-> Project`.
- `activities_and_outputs.collaborators`: de tao mang cong tac `Expert -[:COLLABORATES_WITH]-> Expert`.
- `activities_and_outputs.grant_history`: de noi expert voi funder/grant history.
- `basic_info.location`: de dung tin hieu dia ly khi goi y.
- `academic_profile.current_affiliation`: de noi expert voi enterprise/organization hien tai.

## Project

Can bo sung cac truong sau:

- `basic_info.research_directions`: de tao `Project -[:FOCUSES_ON]-> ResearchDirection`.
- `basic_info.research_topics`: de tao `Project -[:FOCUSES_ON_TOPIC]-> ResearchTopic`.
- `basic_info.keywords`: de ho tro match voi expert/paper/topic.
- `requirements_and_timeline.required_skills`: rat quan trong cho goi y expert qua skill.
- `relations.enterprise_partners`: de train/goi y enterprise phu hop voi project.
- `relations.target_industries`: de noi project voi nganh ung dung.
- `relations.related_projects`: de hoc project tuong tu.
- `rd_profile.outputs`: de noi project voi paper/product/deliverable.
- `rd_profile.required_dataset_ids`: de tao `Project -[:REQUIRES_DATA]-> Dataset`.
- `requirements_and_timeline.budget.amount`: de match voi funder theo quy mo tai tro.
- `basic_info.location`: de match theo vung/quoc gia/thanh pho.

## Funder

Can bo sung cac truong sau:

- `funding_strategy.funding_directions`: de tao `Funder -[:SUPPORTS]-> ResearchDirection`.
- `funding_strategy.funding_topics`: de match funder voi topic cua project.
- `funding_strategy.focus_regions`: de match theo dia ly.
- `funding_strategy.focus_sectors`: de match theo nganh.
- `funding_strategy.eligibility_criteria`: de loc project theo dieu kien tai tro.
- `funding_strategy.typical_grant_size`: de so khop voi budget cua project.
- `programs`: de mo hinh hoc cac chuong trinh tai tro cu the.
- `programs.target_industries`: de noi program/funder voi industry.
- `funding_history.funded_projects`: rat quan trong de tao quan he `Funder -[:FUNDS]-> Project`.
- `relations.invests_in_enterprise_ids`: de noi funder voi enterprise.

## Enterprise

Can bo sung cac truong sau:

- `basic_info.industries`: de tao `Enterprise -[:OPERATES_IN]-> Industry`.
- `rd_profile.rd_focus_directions`: de biet huong R&D cua doanh nghiep.
- `rd_profile.rd_focus_topics`: de match voi project/expert.
- `rd_profile.technology_needs`: de biet doanh nghiep can cong nghe gi.
- `rd_profile.technology_needs.required_skills`: de tao `Enterprise -[:REQUIRES_SKILL]-> Skill`.
- `relations.rd_projects`: de tao `Enterprise -[:PARTNERS_WITH]-> Project`.
- `relations.worked_experts`: de noi enterprise voi expert da lam viec.
- `outputs_and_transfers.commercialized_assets`: de noi enterprise voi product/paper/patent.
- `outputs_and_transfers.transfer_history`: de hoc lich su chuyen giao cong nghe.
- `representatives.rd_contact.expert_id`: de noi doanh nghiep voi nguoi phu trach R&D.

## Paper / Output Asset

Can bo sung/chuan hoa cac truong sau:

- `metadata.keywords`: can day du va chuan hoa thanh topic/skill.
- `metadata.abstract`: can day du hon de trich xuat topic/embedding van ban.
- `metadata.authors`: can co `author_id`/`expert_id`, khong chi ten text.
- `links.produced_by_project`: de noi paper voi project tao ra no.
- `links.commercialized_by`: de noi output voi enterprise.
- DOI/OpenAlex ID/citation count: de danh gia chat luong output.
- venue/publisher: co the dung lam tin hieu chat luong phu.

## Product

Can bo sung/chuan hoa cac truong sau:

- `linked_project_id`: de tao `Project -[:CREATES]-> Product`.
- `developer_ids`: can dam bao map duoc sang expert/enterprise that.
- `type`: can phan biet paper, patent, software, dataset, prototype, product thuong mai.
- `domain_tags` hoac `keywords`: de noi product voi topic.
- `skills_used`: de noi product voi skill/method.
- `industry`: de noi product voi nganh ung dung.
- `commercialized_by`: de noi product voi enterprise.
- `access_url`: khong quan trong cho train, nhung huu ich cho demo/UI.

## Cac quan he quan trong nhat can co

Neu muon train model/PGPR tot, bo du lieu can uu tien tao duoc cac quan he sau:

- `Expert -[:HAS_SKILL]-> Skill`
- `Project -[:REQUIRES_SKILL]-> Skill`
- `Expert -[:RESEARCHES]-> ResearchDirection`
- `Project -[:FOCUSES_ON]-> ResearchDirection`
- `Expert -[:HAS_EXPERIENCE_IN]-> ResearchTopic`
- `Project -[:FOCUSES_ON_TOPIC]-> ResearchTopic`
- `Expert -[:PARTICIPATES_IN]-> Project`
- `Funder -[:FUNDS]-> Project`
- `Funder -[:SUPPORTS_TOPIC]-> ResearchTopic`
- `Enterprise -[:PARTNERS_WITH]-> Project`
- `Enterprise -[:REQUIRES_SKILL]-> Skill`
- `Enterprise -[:OPERATES_IN]-> Industry`
- `Project -[:TARGETS]-> Industry`
- `Expert -[:DEVELOPS]-> Product`
- `Project -[:CREATES]-> Product`
- `Paper/Product -[:HAS_TOPIC]-> ResearchTopic`

## Ket luan ngan

Bo JSONL moi co khung entity dung voi do an, nhung de train model tot can bo sung cac thuoc tinh tao duoc lien ket giua `Expert`, `Project`, `Funder`, `Enterprise`, `Skill`, `ResearchTopic`, `Industry`, `Product/Paper`. Cac field can uu tien nhat la skill, topic, industry, project participation, funding history, enterprise partnership va link project-output.

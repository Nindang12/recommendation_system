"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Edit3, Eye, Loader2, Plus, Save, Trash2, X, User } from "lucide-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Navbar } from "@/components/navigation/navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, UserProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  countryOptions,
  districtOptions,
  firstDistrict,
  firstProvince,
  optionLabel,
  provinceOptions,
  skillOptions,
} from "@/lib/profile-options";
import {
  researchDirectionLabel,
  researchTopicDirection,
  researchTopicLabel,
  researchTopicsByDirection,
} from "@/lib/research-topics";

gsap.registerPlugin(ScrollTrigger);

function statusLabel(value?: string) {
  const labels: Record<string, string> = {
    email_unverified: "Email chưa xác thực",
    email_verified: "Email đã xác thực",
    unverified: "Chưa xác thực",
    pending_review: "Chờ duyệt",
    verified: "Đã xác thực",
    rejected: "Bị từ chối",
    not_synced: "Chưa đồng bộ KG",
    syncing: "Đang đồng bộ KG",
    synced_unverified: "Đã đồng bộ, chưa xác thực",
    synced_verified: "Đã đồng bộ và xác thực",
    merge_required: "Cần kiểm tra trùng",
    sync_failed: "Đồng bộ lỗi",
    sync_partial: "Đồng bộ chưa hoàn tất",
    disabled: "Đã vô hiệu hóa",
  };
  return labels[value || ""] || value || "Không rõ";
}

function roleLabel(value?: string) {
  const labels: Record<string, string> = {
    expert: "Chuyên gia",
    enterprise: "Doanh nghiệp",
    funder: "Nhà tài trợ",
  };
  return labels[value || ""] || value || "Chưa có";
}

function skillLabel(value: string) {
  return skillOptions.find((skill) => skill.value === value)?.label ?? value;
}

function joinLabels(values?: string[], mapper: (value: string) => string = (value) => value) {
  const items = (values ?? []).map(mapper).filter(Boolean);
  return items.length ? items.join(", ") : "Chưa cập nhật";
}

type RoleField = {
  key: string;
  label: string;
  kind?: "text" | "number" | "textarea" | "date" | "select" | "array";
  options?: Array<{ value: string; label: string }>;
  fields?: RoleField[];
  description?: string;
  placeholder?: string;
};

type RoleSection = {
  title: string;
  description?: string;
  fields: RoleField[];
};

const roleSections: Record<string, RoleSection[]> = {
  expert: [
    {
      title: "Thông tin cá nhân",
      fields: [
        { key: "basic_info.birth_date", label: "Ngày sinh", kind: "date" },
        {
          key: "basic_info.gender",
          label: "Giới tính",
          kind: "select",
          options: [
            { value: "male", label: "Nam" },
            { value: "female", label: "Nữ" },
            { value: "other", label: "Khác" },
            { value: "prefer_not_to_say", label: "Không muốn cung cấp" },
          ],
        },
      ],
    },
    {
      title: "Định danh nghiên cứu",
      fields: [
        { key: "identifiers.ORCID", label: "ORCID" },
        { key: "identifiers.ResearcherID", label: "ResearcherID" },
        { key: "identifiers.Scopus_ID", label: "Scopus ID" },
      ],
    },
    {
      title: "Học thuật và năng lực",
      fields: [
        {
          key: "academic_profile.academic_rank",
          label: "Học hàm/học viên",
          kind: "select",
          options: [
            { value: "bachelor", label: "Cử nhân/Kỹ sư" },
            { value: "master", label: "Thạc sĩ" },
            { value: "phd", label: "Tiến sĩ" },
            { value: "associate_professor", label: "Phó giáo sư" },
            { value: "professor", label: "Giáo sư" },
            { value: "other", label: "Khác" },
          ],
        },
        { key: "academic_profile.current_affiliation.org_name", label: "Đơn vị hiện tại" },
        { key: "research_capacity.research_lab", label: "Phòng lab / nhóm nghiên cứu" },
        { key: "academic_metrics.publication_count", label: "Số công bố", kind: "number" },
        { key: "academic_metrics.h_index", label: "H-index", kind: "number" },
        { key: "academic_metrics.citation_count", label: "Số trích dẫn", kind: "number" },
      ],
    },
  ],
  enterprise: [
    {
      title: "Thông tin doanh nghiệp",
      fields: [
        { key: "basic_info.tax_code", label: "Mã số thuế" },
        { key: "basic_info.founded_year", label: "Năm thành lập", kind: "number" },
        { key: "basic_info.industries", label: "Ngành/lĩnh vực", kind: "textarea" },
        { key: "organization_metrics.size", label: "Quy mô" },
        { key: "organization_metrics.income", label: "Doanh thu" },
        { key: "organization_metrics.employees", label: "Số nhân sự", kind: "number" },
      ],
    },
    {
      title: "Liên hệ và R&D",
      fields: [
        { key: "representatives.legal_rep.name", label: "Người đại diện pháp lý" },
        { key: "representatives.contact_person.email", label: "Email liên hệ" },
        { key: "rd_profile.rd_focus_directions", label: "Hướng R&D", kind: "textarea" },
        { key: "rd_profile.technology_needs", label: "Nhu cầu công nghệ", kind: "textarea" },
        { key: "rd_profile.desired_TRL", label: "TRL mong muốn", kind: "number" },
      ],
    },
    {
      title: "Đầu tư và chuyển giao",
      fields: [
        { key: "investment_and_markets.innovation_index", label: "Innovation index", kind: "number" },
        { key: "outputs_and_transfers.commercialized_assets", label: "Tài sản đã thương mại hóa", kind: "textarea" },
        { key: "relations.participated_projects", label: "Dự án đã tham gia", kind: "textarea" },
      ],
    },
  ],
  funder: [
    {
      title: "Thông tin nhà tài trợ",
      fields: [
        { key: "basic_info.type", label: "Loại nhà tài trợ" },
        { key: "basic_info.budget_capacity", label: "Năng lực ngân sách" },
        { key: "representatives.contact_person.name", label: "Người liên hệ" },
        { key: "representatives.contact_person.email", label: "Email liên hệ" },
      ],
    },
    {
      title: "Chiến lược tài trợ",
      fields: [
        { key: "funding_strategy.funding_directions", label: "Hướng tài trợ", kind: "textarea" },
        { key: "funding_strategy.focus_sectors", label: "Lĩnh vực ưu tiên", kind: "textarea" },
        { key: "funding_strategy.trl_range_focus", label: "Khoảng TRL ưu tiên" },
        { key: "funding_strategy.typical_grant_size", label: "Mức tài trợ điển hình" },
        { key: "funding_strategy.eligibility_criteria", label: "Tiêu chí hợp lệ", kind: "textarea" },
      ],
    },
    {
      title: "Chương trình và tác động",
      fields: [
        { key: "programs.program_list", label: "Danh sách chương trình", kind: "textarea" },
        { key: "funding_history.funded_projects", label: "Dự án đã tài trợ", kind: "textarea" },
        { key: "impact_metrics.projects_success_rate", label: "Tỷ lệ dự án thành công", kind: "number" },
        { key: "impact_metrics.commercialization_rate", label: "Tỷ lệ thương mại hóa", kind: "number" },
      ],
    },
  ],
};

const genderOptions = [
  { value: "male", label: "Nam" },
  { value: "female", label: "Nữ" },
  { value: "other", label: "Khác" },
  { value: "prefer_not_to_say", label: "Khong muon cung cap" },
];

const academicRankOptions = [
  { value: "bachelor", label: "Cử nhân/Kỹ sư" },
  { value: "master", label: "Thạc sĩ" },
  { value: "phd", label: "Tiến sĩ" },
  { value: "associate_professor", label: "Phó giáo sư" },
  { value: "professor", label: "Giáo sư" },
  { value: "other", label: "Khác" },
];

const proficiencyOptions = [
  { value: "beginner", label: "Cơ bản" },
  { value: "intermediate", label: "Trung bình" },
  { value: "advanced", label: "Thành thạo" },
  { value: "expert", label: "Chuyên gia" },
];

const statusOptions = [
  { value: "planned", label: "Dự kiến" },
  { value: "ongoing", label: "Đang thực hiện" },
  { value: "completed", label: "Đã hoàn thành" },
  { value: "paused", label: "Tạm dừng" },
];

const fundingTypeOptions = [
  { value: "grant", label: "Grant" },
  { value: "equity", label: "Đầu tư cổ phần" },
  { value: "loan", label: "Khoản vay" },
  { value: "sponsorship", label: "Tài trợ" },
  { value: "other", label: "Khác" },
];

const schemaRoleSections: Record<string, RoleSection[]> = {
  expert: [
    {
      title: "Basic info",
      fields: [
        { key: "basic_info.birth_date", label: "Ngày sinh", kind: "date" },
        { key: "basic_info.gender", label: "Giới tính", kind: "select", options: genderOptions },
      ],
    },
    {
      title: "Định danh và liên hệ",
      fields: [
        { key: "identifiers.ORCID", label: "ORCID" },
        { key: "identifiers.ResearcherID", label: "ResearcherID" },
        { key: "identifiers.Scopus_ID", label: "Scopus ID" },
        { key: "contact_info.preferred_contact_method", label: "Liên hệ ưu tiên", kind: "select", options: [
          { value: "email", label: "Email" },
          { value: "phone", label: "Điện thoại" },
          { value: "linkedin", label: "LinkedIn" },
        ] },
      ],
    },
    {
      title: "Học thuật và năng lực",
      fields: [
        { key: "academic_profile.academic_rank", label: "Học hàm/học viên", kind: "select", options: academicRankOptions },
        { key: "academic_profile.current_affiliation.org_name", label: "Đơn vị hiện tại" },
        { key: "academic_profile.current_affiliation.department", label: "Khoa/phòng ban" },
        { key: "academic_profile.degrees", label: "Bằng cấp", kind: "array", fields: [
          { key: "level", label: "Cấp bậc", kind: "select", options: academicRankOptions },
          { key: "major", label: "Ngành" },
          { key: "institution", label: "Trường/tổ chức" },
          { key: "year_awarded", label: "Năm cấp", kind: "number" },
        ] },
        { key: "academic_profile.affiliation_history", label: "Quá trình công tác", kind: "array", fields: [
          { key: "org", label: "To chuc" },
          { key: "role", label: "Vai trò" },
          { key: "start_date", label: "Từ ngày", kind: "date" },
          { key: "end_date", label: "Đến ngày", kind: "date" },
        ] },
      ],
    },
    {
      title: "Research capacity",
      fields: [
        {
          key: "research_capacity.research_lab",
          label: "Phòng lab / nhóm nghiên cứu",
          description: "Tên lab, nhóm nghiên cứu hoặc trung tâm R&D mà bạn đang tham gia.",
          placeholder: "Ví dụ: AI Healthcare Lab, Computer Vision Group",
        },
        {
          key: "research_capacity.technology",
          label: "Công nghệ",
          kind: "array",
          description: "Các công nghệ, framework, năng lực, thiết bị hoặc tool bạn có khả năng sử dụng cho R&D.",
          fields: [
            {
              key: "name",
              label: "Tên công nghệ",
              placeholder: "Vi du: PyTorch, TensorFlow, Neo4j, Docker, CUDA",
              description: "Ghi tên công nghệ cụ thể thay vì ghi lĩnh vực chung.",
            },
          ],
        },
        { key: "research_capacity.skills_methods", label: "Kỹ năng/phương pháp", kind: "array", fields: [
          { key: "name", label: "Tên kỹ năng", placeholder: "Ví dụ: model training, data labeling, graph modeling" },
          { key: "category", label: "Nhóm", placeholder: "Ví dụ: AI, Data, Software, Domain" },
          { key: "proficiency_level", label: "Mức độ", kind: "select", options: proficiencyOptions },
        ] },
        { key: "research_capacity.applied_industries", label: "Ngành ứng dụng", kind: "array", fields: [
          { key: "code", label: "Mã ngành" },
          { key: "name", label: "Tên ngành" },
        ] },
      ],
    },
    {
      title: "Năng lực học thuật và kết quả",
      fields: [
        { key: "academic_metrics.publication_count", label: "Số công bố", kind: "number" },
        { key: "academic_metrics.h_index", label: "H-index", kind: "number" },
        { key: "academic_metrics.citation_count", label: "Số trích dẫn", kind: "number" },
        { key: "academic_metrics.i10_index", label: "i10-index", kind: "number" },
        { key: "academic_metrics.altmetrics", label: "Altmetrics", kind: "number" },
        { key: "academic_metrics.impact_factor", label: "Hệ số ảnh hưởng", kind: "number" },
      ],
    },
    {
      title: "Activities and outputs",
      fields: [
        { key: "activities_and_outputs.list_outputs", label: "Công bố/sản phẩm", kind: "array", fields: [
          { key: "type", label: "Loai", kind: "select", options: [
            { value: "paper", label: "Bài báo" },
            { value: "patent", label: "Bằng sáng chế" },
            { value: "product", label: "Sản phẩm" },
            { value: "dataset", label: "Dataset" },
          ] },
          { key: "title", label: "Tiêu đề" },
          { key: "year", label: "Năm", kind: "number" },
          { key: "doi", label: "DOI/Mã sản phẩm" },
        ] },
        { key: "activities_and_outputs.collaborators", label: "Công tác viên", kind: "array", fields: [
          { key: "expert_id", label: "Expert ID" },
          { key: "relation_type", label: "Loại quan hệ" },
          { key: "duration", label: "Thời gian" },
        ] },
        { key: "activities_and_outputs.grant_history", label: "Lịch sử grant", kind: "array", fields: [
          { key: "grant_id", label: "Grant ID" },
          { key: "funder_id", label: "Funder ID" },
          { key: "amount", label: "Số tiền", kind: "number" },
          { key: "year", label: "Năm", kind: "number" },
          { key: "linked_project_id", label: "Dự án liên quan" },
        ] },
        { key: "activities_and_outputs.projects_participation", label: "Dự án tham gia", kind: "array", fields: [
          { key: "project_id", label: "Project ID" },
          { key: "role", label: "Vai trò" },
          { key: "duration", label: "Thời gian" },
          { key: "status", label: "Trạng thái", kind: "select", options: statusOptions },
        ] },
      ],
    },
  ],
  enterprise: [
    {
      title: "Thông tin cơ bản và chỉ số",
      fields: [
        { key: "basic_info.tax_code", label: "Mã số thuế" },
        { key: "basic_info.founded_year", label: "Năm thành lập", kind: "number" },
        { key: "basic_info.industries", label: "Nganh/lĩnh vực", kind: "array", fields: [
          { key: "code", label: "Mã ngành" },
          { key: "name", label: "Tên ngành" },
        ] },
        { key: "organization_metrics.size", label: "Quy mô" },
        { key: "organization_metrics.income", label: "Doanh thu" },
        { key: "organization_metrics.employees", label: "Số nhân sự", kind: "number" },
        { key: "organization_metrics.certifications", label: "Chứng nhận", kind: "array", fields: [{ key: "name", label: "Tên chứng nhận" }] },
      ],
    },
    {
      title: "Representatives",
      fields: [
        { key: "representatives.legal_rep.name", label: "Người đại diện pháp lý" },
        { key: "representatives.legal_rep.position", label: "Chức vụ" },
        { key: "representatives.contact_person.name", label: "Người liên hệ" },
        { key: "representatives.contact_person.email", label: "Email liên hệ" },
        { key: "representatives.contact_person.phone", label: "Điện thoại liên hệ" },
      ],
    },
    {
      title: "R&D profile và nhu cầu công nghệ",
      fields: [
        { key: "rd_profile.rd_focus_directions", label: "Hướng R&D", kind: "array", fields: [{ key: "name", label: "Tên hướng" }] },
        { key: "rd_profile.technology_needs", label: "Nhu cầu công nghệ", kind: "array", description: "Những vấn đề công nghệ doanh nghiệp cần chuyên gia/dự án hỗ trợ giải quyết.", fields: [
          { key: "need", label: "Nhu cầu", placeholder: "Ví dụ: dự báo lỗi thiết bị, truy xuất dữ liệu sản xuất" },
          { key: "required_skill", label: "Kỹ năng cần", placeholder: "Ví dụ: predictive maintenance, IoT, computer vision" },
          { key: "proficiency_level", label: "Mức độ", kind: "select", options: proficiencyOptions },
        ] },
        { key: "rd_profile.desired_TRL", label: "TRL mong muốn", kind: "number" },
        { key: "rd_profile.rd_capacity.research_staff", label: "Nhân sự R&D", kind: "number" },
        { key: "rd_profile.rd_capacity.labs", label: "Phòng lab", kind: "array", fields: [{ key: "name", label: "Tên lab" }] },
        { key: "rd_profile.rd_capacity.equipment", label: "Thiết bị", kind: "array", fields: [{ key: "name", label: "Tên thiết bị" }] },
      ],
    },
    {
      title: "Outputs, investment và liên hệ",
      fields: [
        { key: "investment_and_markets.innovation_index", label: "Innovation index", kind: "number" },
        { key: "investment_and_markets.investment_history", label: "Lịch sử đầu tư", kind: "array", fields: [
          { key: "source", label: "Nguồn" },
          { key: "amount", label: "Số tiền", kind: "number" },
          { key: "purpose", label: "Mục đích" },
        ] },
        { key: "outputs_and_transfers.commercialized_assets", label: "Tài sản đã thương mại hóa", kind: "array", fields: [
          { key: "product", label: "Sản phẩm" },
          { key: "year", label: "Nam", kind: "number" },
          { key: "revenue_estimate", label: "Doanh thu ước tính", kind: "number" },
        ] },
        { key: "outputs_and_transfers.patent_outputs", label: "Bằng sáng chế", kind: "array", fields: [
          { key: "type", label: "Loại" },
          { key: "patent_id", label: "Patent ID" },
          { key: "status", label: "Trạng thái", kind: "select", options: statusOptions },
        ] },
        { key: "relations.rd_projects", label: "Dự án R&D", kind: "array", fields: [
          { key: "project_id", label: "Project ID" },
          { key: "role", label: "Vai trò" },
          { key: "status", label: "Trạng thái", kind: "select", options: statusOptions },
        ] },
        { key: "relations.worked_experts", label: "Chuyên gia đã hợp tác", kind: "array", fields: [
          { key: "expert_id", label: "Expert ID" },
          { key: "role", label: "Vai trò" },
          { key: "period", label: "Thời gian" },
        ] },
      ],
    },
  ],
  funder: [
    {
      title: "Thông tin cơ bản và đại diện",
      fields: [
        { key: "basic_info.type", label: "Loại nhà tài trợ", kind: "select", options: fundingTypeOptions },
        { key: "basic_info.budget_capacity", label: "Năng lực ngân sách" },
        { key: "representatives", label: "Đại diện", kind: "array", fields: [
          { key: "name", label: "Tên" },
          { key: "position", label: "Chức vụ" },
          { key: "email", label: "Email" },
          { key: "phone", label: "Điện thoại" },
        ] },
      ],
    },
    {
      title: "Chiến lược tài trợ",
      fields: [
        { key: "funding_strategy.funding_directions", label: "Hướng tài trợ", kind: "array", description: "Các hướng nghiên cứu/đổi mới sáng tạo mà quy ưu tiên cấp vốn.", fields: [{ key: "name", label: "Tên hướng", placeholder: "Ví dụ: AI trong y tế, Năng lực tạo năng lượng" }] },
        { key: "funding_strategy.focus_regions", label: "Vùng ưu tiên", kind: "array", fields: [{ key: "name", label: "Tên vùng" }] },
        { key: "funding_strategy.focus_sectors", label: "Lĩnh vực ưu tiên", kind: "array", fields: [{ key: "name", label: "Tên lĩnh vực" }] },
        { key: "funding_strategy.trl_range_focus.min", label: "TRL tối thiểu", kind: "number" },
        { key: "funding_strategy.trl_range_focus.max", label: "TRL tối đa", kind: "number" },
        { key: "funding_strategy.typical_grant_size", label: "Mức tài trợ điển hình" },
        { key: "funding_strategy.eligibility_criteria", label: "Tiêu chí hợp lệ", kind: "textarea" },
        { key: "funding_strategy.application_process", label: "Quy trình nộp hồ sơ", kind: "textarea" },
      ],
    },
    {
      title: "Chương trình, lịch sử và tác động",
      fields: [
        { key: "programs", label: "Chương trình tài trợ", kind: "array", fields: [
          { key: "program_id", label: "Program ID" },
          { key: "title", label: "Tên chương trình" },
          { key: "application_window", label: "Thời gian nộp" },
          { key: "max_amount", label: "Mức tối đa", kind: "number" },
          { key: "currency", label: "Tiền tệ" },
        ] },
        { key: "funding_history.funded_projects", label: "Dự án đã tài trợ", kind: "array", fields: [
          { key: "project_id", label: "Project ID" },
          { key: "title", label: "Tên dự án" },
          { key: "grant_amount", label: "Số tiền", kind: "number" },
          { key: "year", label: "Năm", kind: "number" },
          { key: "status", label: "Trạng thái", kind: "select", options: statusOptions },
        ] },
        { key: "funding_history.annual_grant_history", label: "Grant theo năm", kind: "array", fields: [
          { key: "year", label: "Năm", kind: "number" },
          { key: "total_amount", label: "Tổng tiền", kind: "number" },
          { key: "recipients", label: "Số bên nhận", kind: "number" },
        ] },
        { key: "impact_metrics.projects_success_rate", label: "Tỷ lệ dự án thành công", kind: "number" },
        { key: "impact_metrics.commercialization_rate", label: "Tỷ lệ thương mại hóa", kind: "number" },
      ],
    },
  ],
};

function getNestedValue(source: Record<string, unknown> | undefined, path: string) {
  return path.split(".").reduce<unknown>((current, key) => {
    if (!current || typeof current !== "object") return undefined;
    return (current as Record<string, unknown>)[key];
  }, source);
}

function setNestedValue(source: Record<string, unknown> | undefined, path: string, value: unknown) {
  const next = structuredClone(source ?? {}) as Record<string, unknown>;
  const keys = path.split(".");
  let current = next;
  keys.slice(0, -1).forEach((key) => {
    if (!current[key] || typeof current[key] !== "object") current[key] = {};
    current = current[key] as Record<string, unknown>;
  });
  current[keys[keys.length - 1]] = value;
  return next;
}

export default function ProfilePage() {
  const router = useRouter();
  const { user, isLoading, refresh } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [useCustomSkill, setUseCustomSkill] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const topicGroups = researchTopicsByDirection();

  useEffect(() => {
    if (!isLoading && !user) router.push("/auth/login");
    if (user) {
      setProfile(user);
      setUseCustomSkill((user.custom_skills ?? []).length > 0);
    }
  }, [isLoading, router, user]);

  useEffect(() => {
    if (!isLoading && user) {
      void refresh();
    }
  }, [isLoading]);

  useEffect(() => {
    if (!profile || isEditing) return;
    const context = gsap.context(() => {
      gsap.fromTo(
        ".profile-reveal",
        { y: 18, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.55,
          ease: "power2.out",
          stagger: 0.06,
          scrollTrigger: {
            trigger: ".profile-shell",
            start: "top 82%",
            once: true,
          },
        },
      );
      gsap.fromTo(
        ".profile-detail-reveal",
        { y: 24, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.5,
          ease: "power2.out",
          stagger: 0.04,
          scrollTrigger: {
            trigger: ".profile-detail",
            start: "top 86%",
            once: true,
          },
        },
      );
    });
    return () => context.revert();
  }, [showDetails, isEditing]);

  function updateProfile(patch: Partial<UserProfile>) {
    if (!profile || !isEditing) return;
    setProfile({ ...profile, ...patch });
    setIsDirty(true);
    setMessage("");
  }

  function cancelEdit() {
    setProfile(user);
    setUseCustomSkill((user?.custom_skills ?? []).length > 0);
    setIsEditing(false);
    setIsDirty(false);
    setMessage("");
  }

  async function handleSave() {
    if (!profile || !isDirty) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await api.updateMe(profile);
      setProfile(response.data);
      await refresh();
      setIsEditing(false);
      setIsDirty(false);
      setMessage("Da luu profile.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Lưu hồ sơ thất bại");
    } finally {
      setSaving(false);
    }
  }

  function toggleTopic(topic: string, checked: boolean | "indeterminate") {
    if (!profile || !isEditing) return;
    const current = profile.research_interests ?? [];
    updateProfile({
      research_interests:
        checked === true ? Array.from(new Set([...current, topic])) : current.filter((item) => item !== topic),
    });
  }

  function toggleSkill(skill: string, checked: boolean | "indeterminate") {
    if (!profile || !isEditing) return;
    const current = profile.skills ?? [];
    updateProfile({
      skills: checked === true ? Array.from(new Set([...current, skill])) : current.filter((item) => item !== skill),
    });
  }

  function updateCustomTopics(value: string) {
    updateProfile({
      custom_research_topics: value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  function updateCustomSkills(value: string) {
    updateProfile({
      custom_skills: value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  function updateSocialLink(key: string, value: string) {
    updateProfile({
      social_links: {
        ...(profile?.social_links ?? {}),
        [key]: value,
      },
    });
  }

  function updateProfileData(path: string, value: unknown) {
    updateProfile({ profile_data: setNestedValue(profile?.profile_data, path, value) });
  }

  function emptyArrayItem(field: RoleField) {
    return Object.fromEntries((field.fields ?? []).map((child) => [child.key, ""]));
  }

  function addArrayItem(path: string, field: RoleField) {
    const current = getNestedValue(profile?.profile_data, path);
    const items = Array.isArray(current) ? current : [];
    updateProfileData(path, [...items, emptyArrayItem(field)]);
  }

  function removeArrayItem(path: string, index: number) {
    const current = getNestedValue(profile?.profile_data, path);
    const items = Array.isArray(current) ? current : [];
    updateProfileData(
      path,
      items.filter((_, itemIndex) => itemIndex !== index),
    );
  }

  function updateArrayItem(path: string, index: number, key: string, value: unknown) {
    const current = getNestedValue(profile?.profile_data, path);
    const items = Array.isArray(current) ? [...current] : [];
    const item = typeof items[index] === "object" && items[index] !== null ? { ...(items[index] as Record<string, unknown>) } : {};
    item[key] = value;
    items[index] = item;
    updateProfileData(path, items);
  }

  function renderScalarField(field: RoleField, value: unknown, onChange: (value: string) => void) {
    const textValue = value === undefined || value === null ? "" : String(value);
    if (field.kind === "textarea") {
      return (
        <Textarea
          lang="vi"
          disabled={!isEditing}
          value={textValue}
          onChange={(event) => onChange(event.target.value)}
          rows={3}
          placeholder={field.placeholder}
        />
      );
    }
    if (field.kind === "select") {
      return (
        <Select disabled={!isEditing} value={textValue} onValueChange={onChange}>
          <SelectTrigger>
            <SelectValue placeholder={`Chon ${field.label.toLowerCase()}`} />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }
    return (
      <Input
        lang="vi"
        disabled={!isEditing}
        type={field.kind === "number" ? "number" : field.kind === "date" ? "date" : "text"}
        value={textValue}
        onChange={(event) => onChange(event.target.value)}
        placeholder={field.placeholder}
      />
    );
  }

  function renderRoleField(field: RoleField) {
    if (field.kind === "array") {
      const value = getNestedValue(profile?.profile_data, field.key);
      const items = Array.isArray(value) ? value : [];
      return (
        <div key={field.key} className="space-y-3 md:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div>
              <Label>{field.label}</Label>
              {field.description ? <p className="mt-1 text-xs text-muted-foreground">{field.description}</p> : null}
            </div>
            {isEditing ? (
              <Button type="button" size="sm" variant="outline" onClick={() => addArrayItem(field.key, field)}>
                <Plus className="mr-2 h-4 w-4" />
                Thêm mục
              </Button>
            ) : null}
          </div>
          <div className="space-y-3">
            {items.length === 0 ? (
              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">Chưa có dữ liệu.</div>
            ) : (
              items.map((item, index) => {
                const itemRecord = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
                return (
                  <div key={`${field.key}-${index}`} className="rounded-md border bg-slate-50 p-3">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold">
                        {field.label} #{index + 1}
                      </div>
                      {isEditing ? (
                        <Button type="button" size="icon" variant="ghost" onClick={() => removeArrayItem(field.key, index)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      ) : null}
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      {(field.fields ?? []).map((child) => (
                        <div key={child.key} className={child.kind === "textarea" ? "space-y-2 md:col-span-2" : "space-y-2"}>
                          <Label>{child.label}</Label>
                          {child.description ? <p className="text-xs text-muted-foreground">{child.description}</p> : null}
                          {renderScalarField(child, itemRecord[child.key], (nextValue) => updateArrayItem(field.key, index, child.key, nextValue))}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      );
    }
    const value = getNestedValue(profile?.profile_data, field.key);
    return (
      <div key={field.key} className={field.kind === "textarea" ? "space-y-2 md:col-span-2" : "space-y-2"}>
        <Label>{field.label}</Label>
        {field.description ? <p className="text-xs text-muted-foreground">{field.description}</p> : null}
        {renderScalarField(field, value, (nextValue) => updateProfileData(field.key, nextValue))}
      </div>
    );
  }

  const selectedResearchDirections = Array.from(
    new Set((profile?.research_interests ?? []).map((topic) => researchTopicDirection(topic)).filter(Boolean) as string[]),
  );

  if (isLoading || !profile) {
    return (
      <div className="min-h-svh bg-background">
        <Navbar />
        <div className="flex h-[60vh] items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      </div>
    );
  }

  const countries = countryOptions();
  const provinces = provinceOptions(profile.country ?? "VN");
  const districts = districtOptions(profile.country ?? "VN", profile.province ?? "");
  const locationText = [
    profile.district,
    optionLabel(provinces, profile.province),
    optionLabel(countries, profile.country),
  ]
    .filter(Boolean)
    .join(", ");
  const sections = schemaRoleSections[profile.role ?? "expert"] ?? schemaRoleSections.expert;

  return (
    <div className="min-h-svh bg-background">
      <Navbar />
      <main className="profile-shell mx-auto max-w-6xl px-4 py-8">
        <header className="profile-reveal mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <User className="h-8 w-8" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Trang cá nhân</h1>
              <p className="text-muted-foreground">Thông tin cơ bản, profile chi tiết và dữ liệu dùng cho recommendation.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setShowDetails((value) => !value)}>
              <Eye className="mr-2 h-4 w-4" />
              {showDetails ? "Ẩn chi tiết" : "Xem thông tin chi tiết"}
            </Button>
            {isEditing ? (
              <Button type="button" variant="outline" onClick={cancelEdit}>
                <X className="mr-2 h-4 w-4" />
                Hủy chỉnh sửa
              </Button>
            ) : (
              <Button
                type="button"
                onClick={() => {
                  setIsEditing(true);
                  setShowDetails(true);
                }}
              >
                <Edit3 className="mr-2 h-4 w-4" />
                Chỉnh sửa
              </Button>
            )}
          </div>
        </header>

        <section className="profile-reveal mb-6 rounded-md border bg-card p-5 shadow-sm">
          <div className="grid gap-5 md:grid-cols-[1.4fr_1fr_1fr]">
            <div>
              <div className="text-sm text-muted-foreground">{roleLabel(profile.role)}</div>
              <div className="mt-1 text-2xl font-bold">{profile.full_name || "Chưa cập nhật tên"}</div>
              <div className="mt-2 text-sm text-muted-foreground">{profile.email}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="secondary" className="rounded-md">
                  {statusLabel(profile.account_verification_status)}
                </Badge>
                <Badge variant="outline" className="rounded-md">
                  {statusLabel(profile.linked_entity?.entity_verification_status)}
                </Badge>
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Tổ chức</div>
              <div className="mt-2 font-medium">{profile.organization || "Chua cap nhat"}</div>
              <div className="mt-4 text-xs font-semibold uppercase text-muted-foreground">Địa điểm</div>
              <div className="mt-2 font-medium">{locationText || "Chua cap nhat"}</div>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase text-muted-foreground">Knowledge Graph</div>
              <Badge variant="outline" className="mt-2 rounded-md">
                {statusLabel(profile.linked_entity?.kg_sync_status)}
              </Badge>
              <div className="mt-4 text-xs font-semibold uppercase text-muted-foreground">Trust weight</div>
              <div className="mt-1 text-2xl font-bold">{Math.round((profile.linked_entity?.trust_weight ?? 1) * 100)}%</div>
            </div>
          </div>
          <div className="mt-5 grid gap-3 border-t pt-4 text-sm md:grid-cols-3">
            <div>
              <span className="text-muted-foreground">Linked entity: </span>
              <span className="font-medium">{profile.linked_entity?.name || profile.linked_entity?.id || "Chua co"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Scope: </span>
              <span className="font-medium">{profile.linked_entity?.participation_scope || "public"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Match: </span>
              <span className="font-medium">{profile.linked_entity?.match_status || "existing"}</span>
            </div>
          </div>
        </section>

        {profile.linked_entity?.kg_sync_status === "synced_unverified" ? (
          <p className="profile-reveal mb-6 rounded-md border bg-secondary/40 p-3 text-sm text-muted-foreground">
            Hồ sơ của bạn đã được đưa vào Knowledge Graph ở trạng thái chưa xác thực. Bạn có thể dùng để nhận gợi ý cá nhân,
            nhưng kết quả có thể thay đổi sau khi được duyệt.
          </p>
        ) : null}

        {profile.linked_entity?.match_status === "matched_existing" ? (
          <p className="profile-reveal mb-6 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
            Hệ thống đã tìm thấy hồ sơ có sẵn khớp với thông tin đăng ký của bạn và đã liên kết tài khoản với entity này.
            Dữ liệu này được xem là entity có sẵn của hệ thống, nên có thể dùng để recommendation với trust weight đầy đủ.
          </p>
        ) : null}

        {profile.linked_entity?.kg_sync_status === "merge_required" &&
        (profile.linked_entity?.duplicate_candidates?.length ?? 0) > 0 ? (
          <p className="profile-reveal mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            Hệ thống phát hiện hồ sơ có khả năng trùng với dữ liệu đã có. Cần admin review/merge trước khi public rộng rãi.
          </p>
        ) : null}

        {showDetails || isEditing ? (
          <section className="profile-detail rounded-md border bg-card p-6 shadow-sm">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-2xl font-bold">Thông tin chi tiết</h2>
                <p className="text-sm text-muted-foreground">
                  {isEditing
                    ? "Các trường đều không bắt buộc. Bạn có thể bổ sung dần để hệ thống gợi ý tốt hơn."
                    : "Bấm Chỉnh sửa nếu muốn cập nhật các thông tin này."}
                </p>
              </div>
              {isEditing ? <Badge className="rounded-md">Đang chỉnh sửa</Badge> : null}
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="profile-detail-reveal space-y-2">
                <Label>Họ tên / tên đơn vị</Label>
                <Input disabled={!isEditing} value={profile.full_name} onChange={(e) => updateProfile({ full_name: e.target.value })} />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Tên người dùng</Label>
                <Input disabled={!isEditing} value={profile.username ?? ""} onChange={(e) => updateProfile({ username: e.target.value })} />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Email</Label>
                <Input value={profile.email} disabled />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Website / profile URL</Label>
                <Input
                  disabled={!isEditing}
                  value={profile.social_links?.website ?? ""}
                  onChange={(e) => updateSocialLink("website", e.target.value)}
                  placeholder="https://..."
                />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>LinkedIn</Label>
                <Input
                  disabled={!isEditing}
                  value={profile.social_links?.linkedin ?? ""}
                  onChange={(e) => updateSocialLink("linkedin", e.target.value)}
                  placeholder="https://linkedin.com/in/..."
                />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Google Scholar</Label>
                <Input
                  disabled={!isEditing}
                  value={profile.social_links?.google_scholar ?? ""}
                  onChange={(e) => updateSocialLink("google_scholar", e.target.value)}
                  placeholder="https://scholar.google.com/..."
                />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>ORCID</Label>
                <Input
                  disabled={!isEditing}
                  value={profile.social_links?.orcid ?? ""}
                  onChange={(e) => updateSocialLink("orcid", e.target.value)}
                  placeholder="https://orcid.org/..."
                />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Vai tro</Label>
                <Select disabled={!isEditing} value={profile.role ?? "expert"} onValueChange={(value) => updateProfile({ role: value })}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="expert">Chuyen gia / Nha nghien cuu</SelectItem>
                    <SelectItem value="enterprise">Doanh nghiep</SelectItem>
                    <SelectItem value="funder">Nha tai tro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>To chuc</Label>
                <Input disabled={!isEditing} value={profile.organization ?? ""} onChange={(e) => updateProfile({ organization: e.target.value })} />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>So dien thoai</Label>
                <Input disabled={!isEditing} value={profile.phone ?? ""} onChange={(e) => updateProfile({ phone: e.target.value })} />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Country</Label>
                <Select
                  disabled={!isEditing}
                  value={profile.country ?? "VN"}
                  onValueChange={(value) => {
                    const nextProvince = firstProvince(value);
                    const nextDistrict = firstDistrict(value, nextProvince);
                    updateProfile({ country: value, province: nextProvince, district: nextDistrict });
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={optionLabel(countries, profile.country)} />
                  </SelectTrigger>
                  <SelectContent>
                    {countries.map((country) => (
                      <SelectItem key={country.value} value={country.value}>
                        {country.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Tinh / Thanh</Label>
                <Select
                  disabled={!isEditing}
                  value={profile.province ?? ""}
                  onValueChange={(value) => {
                    const nextDistrict = firstDistrict(profile.country ?? "VN", value);
                    updateProfile({ province: value, district: nextDistrict });
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Chon tinh/thanh" />
                  </SelectTrigger>
                  <SelectContent>
                    {provinces.map((province) => (
                      <SelectItem key={province.value} value={province.value}>
                        {province.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Quan / Huyen</Label>
                <Select disabled={!isEditing} value={profile.district ?? ""} onValueChange={(value) => updateProfile({ district: value })}>
                  <SelectTrigger>
                    <SelectValue placeholder="Chon quan/huyen" />
                  </SelectTrigger>
                  <SelectContent>
                    {districts.map((district) => (
                      <SelectItem key={district.value} value={district.value}>
                        {district.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="profile-detail-reveal space-y-6 md:col-span-2">
                <div className="border-t pt-5">
                  <h3 className="text-xl font-bold">Thong tin rieng cho {roleLabel(profile.role)}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Nhap cac thong tin co ban cua {roleLabel(profile.role)} truoc. Khong bat buoc nhap het, nhung cang day du thi matching va XAI cang tot.
                  </p>
                </div>
                {sections.map((section) => (
                  <div key={section.title} className="rounded-md border p-4">
                    <div className="mb-4">
                      <h4 className="font-semibold">{section.title}</h4>
                      {section.description ? <p className="text-sm text-muted-foreground">{section.description}</p> : null}
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      {section.fields.map(renderRoleField)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="profile-detail-reveal space-y-2 md:col-span-2">
                <div>
                  <Label>Ky nang / chuyen mon</Label>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {joinLabels(profile.skills, skillLabel)}
                    {(profile.custom_skills ?? []).length ? `, ${profile.custom_skills?.join(", ")}` : ""}
                  </p>
                </div>
                <div className="grid gap-2 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-3">
                  {skillOptions.map((skill) => (
                    <label key={skill.value} className="flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm hover:bg-secondary">
                      <Checkbox
                        disabled={!isEditing}
                        checked={(profile.skills ?? []).includes(skill.value)}
                        onCheckedChange={(checked) => toggleSkill(skill.value, checked)}
                      />
                      {skill.label}
                    </label>
                  ))}
                  <label className="flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm hover:bg-secondary">
                    <Checkbox
                      disabled={!isEditing}
                      checked={useCustomSkill}
                      onCheckedChange={(checked) => {
                        const enabled = checked === true;
                        setUseCustomSkill(enabled);
                        if (!enabled) updateProfile({ custom_skills: [] });
                      }}
                    />
                    Khac
                  </label>
                </div>
                {useCustomSkill ? (
                  <div className="mt-3 space-y-2">
                    <Label>Ky nang khac</Label>
                    <Input
                      disabled={!isEditing}
                      value={(profile.custom_skills ?? []).join(", ")}
                      onChange={(e) => updateCustomSkills(e.target.value)}
                      placeholder="Vi du: MLOps, GIS, Bioinformatics"
                    />
                  </div>
                ) : null}
              </div>
              <div className="profile-detail-reveal space-y-2 md:col-span-2">
                <div>
                  <Label>Chu de nghien cuu</Label>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {joinLabels(profile.research_interests, researchTopicLabel)}
                    {(profile.custom_research_topics ?? []).length ? `, ${profile.custom_research_topics?.join(", ")}` : ""}
                  </p>
                  {selectedResearchDirections.length ? (
                    <p className="mt-2 rounded-md border bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                      Huong nghien cuu tu dong: {selectedResearchDirections.map(researchDirectionLabel).join(", ")}
                    </p>
                  ) : null}
                </div>
                <div className="space-y-4 rounded-md border p-3">
                  {topicGroups.map((group) => (
                    <div key={group.value} className="rounded-md border bg-slate-50 p-3">
                      <div className="mb-3 text-xs font-semibold uppercase text-muted-foreground">{group.label}</div>
                      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {group.topics.map((topic) => (
                          <label
                            key={topic.value}
                            className="flex cursor-pointer items-start gap-2 rounded-md bg-white p-2 text-sm hover:bg-secondary"
                          >
                            <Checkbox
                              disabled={!isEditing}
                              checked={(profile.research_interests ?? []).includes(topic.value)}
                              onCheckedChange={(checked) => toggleTopic(topic.value, checked)}
                            />
                            <span>
                              <span className="block font-medium">{topic.label}</span>
                              <span className="block text-[11px] text-muted-foreground">
                                {researchDirectionLabel(topic.direction)}
                              </span>
                            </span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                  <label className="flex items-center gap-2 rounded-md p-2 text-sm text-muted-foreground">
                    <Checkbox checked={(profile.custom_research_topics ?? []).length > 0} disabled />
                    Khac
                  </label>
                </div>
                <div className="space-y-2">
                  <Label>Chu de nghien cuu khac</Label>
                  <Input
                    disabled={!isEditing}
                    value={(profile.custom_research_topics ?? []).join(", ")}
                    onChange={(e) => updateCustomTopics(e.target.value)}
                    placeholder="Vi du: Federated Learning, Digital Twin"
                  />
                  <p className="text-xs text-muted-foreground">Chu de khac duoc luu rieng de mapping/duyet truoc khi dua vao Neo4j.</p>
                </div>
              </div>
              <div className="profile-detail-reveal space-y-2 md:col-span-2">
                <Label>Mo ta ngan</Label>
                <Textarea disabled={!isEditing} value={profile.bio ?? ""} onChange={(e) => updateProfile({ bio: e.target.value })} rows={5} />
              </div>

            </div>

            {message ? <div className="mt-5 rounded-md border bg-secondary/50 p-3 text-sm">{message}</div> : null}

            {isEditing && isDirty ? (
              <div className="mt-6 flex justify-end border-t pt-5">
                <Button onClick={handleSave} disabled={saving}>
                  {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                  Luu thay doi
                </Button>
              </div>
            ) : null}
          </section>
        ) : null}

        {!showDetails && !isEditing && message ? (
          <div className="rounded-md border bg-secondary/50 p-3 text-sm">{message}</div>
        ) : null}
      </main>
    </div>
  );
}

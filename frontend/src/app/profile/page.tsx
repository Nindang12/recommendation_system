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
    email_unverified: "Email chua xac thuc",
    email_verified: "Email da xac thuc",
    unverified: "Chua xac thuc",
    pending_review: "Cho duyet",
    verified: "Da xac thuc",
    rejected: "Bi tu choi",
    not_synced: "Chua sync KG",
    syncing: "Dang sync KG",
    synced_unverified: "Da sync, chua xac thuc",
    synced_verified: "Da sync va verified",
    merge_required: "Can kiem tra trung",
    sync_failed: "Sync loi",
    sync_partial: "Sync chua hoan tat",
    disabled: "Da vo hieu hoa",
  };
  return labels[value || ""] || value || "Khong ro";
}

function roleLabel(value?: string) {
  const labels: Record<string, string> = {
    expert: "Chuyen gia",
    enterprise: "Doanh nghiep",
    funder: "Nha tai tro",
  };
  return labels[value || ""] || value || "Chua co";
}

function skillLabel(value: string) {
  return skillOptions.find((skill) => skill.value === value)?.label ?? value;
}

function joinLabels(values?: string[], mapper: (value: string) => string = (value) => value) {
  const items = (values ?? []).map(mapper).filter(Boolean);
  return items.length ? items.join(", ") : "Chua cap nhat";
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
      title: "Thong tin ca nhan",
      fields: [
        { key: "basic_info.birth_date", label: "Ngay sinh", kind: "date" },
        {
          key: "basic_info.gender",
          label: "Gioi tinh",
          kind: "select",
          options: [
            { value: "male", label: "Nam" },
            { value: "female", label: "Nu" },
            { value: "other", label: "Khac" },
            { value: "prefer_not_to_say", label: "Khong muon cung cap" },
          ],
        },
      ],
    },
    {
      title: "Dinh danh nghien cuu",
      fields: [
        { key: "identifiers.ORCID", label: "ORCID" },
        { key: "identifiers.ResearcherID", label: "ResearcherID" },
        { key: "identifiers.Scopus_ID", label: "Scopus ID" },
      ],
    },
    {
      title: "Hoc thuat va nang luc",
      fields: [
        {
          key: "academic_profile.academic_rank",
          label: "Hoc ham/hoc vi",
          kind: "select",
          options: [
            { value: "bachelor", label: "Cu nhan/Ky su" },
            { value: "master", label: "Thac si" },
            { value: "phd", label: "Tien si" },
            { value: "associate_professor", label: "Pho giao su" },
            { value: "professor", label: "Giao su" },
            { value: "other", label: "Khac" },
          ],
        },
        { key: "academic_profile.current_affiliation.org_name", label: "Don vi hien tai" },
        { key: "research_capacity.research_lab", label: "Phong lab / nhom nghien cuu" },
        { key: "academic_metrics.publication_count", label: "So cong bo", kind: "number" },
        { key: "academic_metrics.h_index", label: "H-index", kind: "number" },
        { key: "academic_metrics.citation_count", label: "So trich dan", kind: "number" },
      ],
    },
  ],
  enterprise: [
    {
      title: "Thong tin doanh nghiep",
      fields: [
        { key: "basic_info.tax_code", label: "Ma so thue" },
        { key: "basic_info.founded_year", label: "Nam thanh lap", kind: "number" },
        { key: "basic_info.industries", label: "Nganh/lĩnh vuc", kind: "textarea" },
        { key: "organization_metrics.size", label: "Quy mo" },
        { key: "organization_metrics.income", label: "Doanh thu" },
        { key: "organization_metrics.employees", label: "So nhan su", kind: "number" },
      ],
    },
    {
      title: "Lien he va R&D",
      fields: [
        { key: "representatives.legal_rep.name", label: "Nguoi dai dien phap ly" },
        { key: "representatives.contact_person.email", label: "Email lien he" },
        { key: "rd_profile.rd_focus_directions", label: "Huong R&D", kind: "textarea" },
        { key: "rd_profile.technology_needs", label: "Nhu cau cong nghe", kind: "textarea" },
        { key: "rd_profile.desired_TRL", label: "TRL mong muon", kind: "number" },
      ],
    },
    {
      title: "Dau tu va chuyen giao",
      fields: [
        { key: "investment_and_markets.innovation_index", label: "Innovation index", kind: "number" },
        { key: "outputs_and_transfers.commercialized_assets", label: "Tai san da thuong mai hoa", kind: "textarea" },
        { key: "relations.participated_projects", label: "Project da tham gia", kind: "textarea" },
      ],
    },
  ],
  funder: [
    {
      title: "Thong tin nha tai tro",
      fields: [
        { key: "basic_info.type", label: "Loai nha tai tro" },
        { key: "basic_info.budget_capacity", label: "Nang luc ngan sach" },
        { key: "representatives.contact_person.name", label: "Nguoi lien he" },
        { key: "representatives.contact_person.email", label: "Email lien he" },
      ],
    },
    {
      title: "Chien luoc tai tro",
      fields: [
        { key: "funding_strategy.funding_directions", label: "Huong tai tro", kind: "textarea" },
        { key: "funding_strategy.focus_sectors", label: "Linh vuc uu tien", kind: "textarea" },
        { key: "funding_strategy.trl_range_focus", label: "Khoang TRL uu tien" },
        { key: "funding_strategy.typical_grant_size", label: "Muc tai tro dien hinh" },
        { key: "funding_strategy.eligibility_criteria", label: "Tieu chi hop le", kind: "textarea" },
      ],
    },
    {
      title: "Chuong trinh va tac dong",
      fields: [
        { key: "programs.program_list", label: "Danh sach chuong trinh", kind: "textarea" },
        { key: "funding_history.funded_projects", label: "Project da tai tro", kind: "textarea" },
        { key: "impact_metrics.projects_success_rate", label: "Ty le project thanh cong", kind: "number" },
        { key: "impact_metrics.commercialization_rate", label: "Ty le thuong mai hoa", kind: "number" },
      ],
    },
  ],
};

const genderOptions = [
  { value: "male", label: "Nam" },
  { value: "female", label: "Nu" },
  { value: "other", label: "Khac" },
  { value: "prefer_not_to_say", label: "Khong muon cung cap" },
];

const academicRankOptions = [
  { value: "bachelor", label: "Cu nhan/Ky su" },
  { value: "master", label: "Thac si" },
  { value: "phd", label: "Tien si" },
  { value: "associate_professor", label: "Pho giao su" },
  { value: "professor", label: "Giao su" },
  { value: "other", label: "Khac" },
];

const proficiencyOptions = [
  { value: "beginner", label: "Co ban" },
  { value: "intermediate", label: "Trung binh" },
  { value: "advanced", label: "Thanh thao" },
  { value: "expert", label: "Chuyen gia" },
];

const statusOptions = [
  { value: "planned", label: "Du kien" },
  { value: "ongoing", label: "Dang thuc hien" },
  { value: "completed", label: "Da hoan thanh" },
  { value: "paused", label: "Tam dung" },
];

const fundingTypeOptions = [
  { value: "grant", label: "Grant" },
  { value: "equity", label: "Dau tu co phan" },
  { value: "loan", label: "Khoan vay" },
  { value: "sponsorship", label: "Tai tro" },
  { value: "other", label: "Khac" },
];

const schemaRoleSections: Record<string, RoleSection[]> = {
  expert: [
    {
      title: "Basic info",
      fields: [
        { key: "basic_info.birth_date", label: "Ngay sinh", kind: "date" },
        { key: "basic_info.gender", label: "Gioi tinh", kind: "select", options: genderOptions },
      ],
    },
    {
      title: "Identifiers va lien he",
      fields: [
        { key: "identifiers.ORCID", label: "ORCID" },
        { key: "identifiers.ResearcherID", label: "ResearcherID" },
        { key: "identifiers.Scopus_ID", label: "Scopus ID" },
        { key: "contact_info.preferred_contact_method", label: "Lien he uu tien", kind: "select", options: [
          { value: "email", label: "Email" },
          { value: "phone", label: "Dien thoai" },
          { value: "linkedin", label: "LinkedIn" },
        ] },
      ],
    },
    {
      title: "Academic profile",
      fields: [
        { key: "academic_profile.academic_rank", label: "Hoc ham/hoc vi", kind: "select", options: academicRankOptions },
        { key: "academic_profile.current_affiliation.org_name", label: "Don vi hien tai" },
        { key: "academic_profile.current_affiliation.department", label: "Khoa/phong ban" },
        { key: "academic_profile.degrees", label: "Bang cap", kind: "array", fields: [
          { key: "level", label: "Cap bac", kind: "select", options: academicRankOptions },
          { key: "major", label: "Nganh" },
          { key: "institution", label: "Truong/to chuc" },
          { key: "year_awarded", label: "Nam cap", kind: "number" },
        ] },
        { key: "academic_profile.affiliation_history", label: "Qua trinh cong tac", kind: "array", fields: [
          { key: "org", label: "To chuc" },
          { key: "role", label: "Vai tro" },
          { key: "start_date", label: "Tu ngay", kind: "date" },
          { key: "end_date", label: "Den ngay", kind: "date" },
        ] },
      ],
    },
    {
      title: "Research capacity",
      fields: [
        {
          key: "research_capacity.research_lab",
          label: "Phong lab / nhom nghien cuu",
          description: "Ten lab, nhom nghien cuu hoac trung tam R&D ma ban dang tham gia.",
          placeholder: "Vi du: AI Healthcare Lab, Computer Vision Group",
        },
        {
          key: "research_capacity.technology",
          label: "Cong nghe",
          kind: "array",
          description: "Cac cong nghe, framework, nen tang, thiet bi hoac tool ban co kha nang su dung cho R&D.",
          fields: [
            {
              key: "name",
              label: "Ten cong nghe",
              placeholder: "Vi du: PyTorch, TensorFlow, Neo4j, Docker, CUDA",
              description: "Ghi ten cong nghe cu the thay vi ghi linh vuc chung.",
            },
          ],
        },
        { key: "research_capacity.skills_methods", label: "Ky nang/phuong phap", kind: "array", fields: [
          { key: "name", label: "Ten ky nang", placeholder: "Vi du: model training, data labeling, graph modeling" },
          { key: "category", label: "Nhom", placeholder: "Vi du: AI, Data, Software, Domain" },
          { key: "proficiency_level", label: "Muc do", kind: "select", options: proficiencyOptions },
        ] },
        { key: "research_capacity.applied_industries", label: "Nganh ung dung", kind: "array", fields: [
          { key: "code", label: "Ma nganh" },
          { key: "name", label: "Ten nganh" },
        ] },
      ],
    },
    {
      title: "Academic metrics",
      fields: [
        { key: "academic_metrics.publication_count", label: "So cong bo", kind: "number" },
        { key: "academic_metrics.h_index", label: "H-index", kind: "number" },
        { key: "academic_metrics.citation_count", label: "So trich dan", kind: "number" },
        { key: "academic_metrics.i10_index", label: "i10-index", kind: "number" },
        { key: "academic_metrics.altmetrics", label: "Altmetrics", kind: "number" },
      ],
    },
    {
      title: "Activities and outputs",
      fields: [
        { key: "activities_and_outputs.list_outputs", label: "Cong bo/san pham", kind: "array", fields: [
          { key: "type", label: "Loai", kind: "select", options: [
            { value: "paper", label: "Bai bao" },
            { value: "patent", label: "Bang sang che" },
            { value: "product", label: "San pham" },
            { value: "dataset", label: "Dataset" },
          ] },
          { key: "title", label: "Tieu de" },
          { key: "year", label: "Nam", kind: "number" },
          { key: "doi", label: "DOI/Product ID" },
        ] },
        { key: "activities_and_outputs.collaborators", label: "Cong tac vien", kind: "array", fields: [
          { key: "expert_id", label: "Expert ID" },
          { key: "relation_type", label: "Loai quan he" },
          { key: "duration", label: "Thoi gian" },
        ] },
        { key: "activities_and_outputs.grant_history", label: "Lich su grant", kind: "array", fields: [
          { key: "grant_id", label: "Grant ID" },
          { key: "funder_id", label: "Funder ID" },
          { key: "amount", label: "So tien", kind: "number" },
          { key: "year", label: "Nam", kind: "number" },
          { key: "linked_project_id", label: "Project lien quan" },
        ] },
        { key: "activities_and_outputs.projects_participation", label: "Project tham gia", kind: "array", fields: [
          { key: "project_id", label: "Project ID" },
          { key: "role", label: "Vai tro" },
          { key: "duration", label: "Thoi gian" },
          { key: "status", label: "Trang thai", kind: "select", options: statusOptions },
        ] },
      ],
    },
  ],
  enterprise: [
    {
      title: "Basic info va metrics",
      fields: [
        { key: "basic_info.tax_code", label: "Ma so thue" },
        { key: "basic_info.founded_year", label: "Nam thanh lap", kind: "number" },
        { key: "basic_info.industries", label: "Nganh/lĩnh vực", kind: "array", fields: [
          { key: "code", label: "Ma nganh" },
          { key: "name", label: "Ten nganh" },
        ] },
        { key: "organization_metrics.size", label: "Quy mo" },
        { key: "organization_metrics.income", label: "Doanh thu" },
        { key: "organization_metrics.employees", label: "So nhan su", kind: "number" },
        { key: "organization_metrics.certifications", label: "Chung nhan", kind: "array", fields: [{ key: "name", label: "Ten chung nhan" }] },
      ],
    },
    {
      title: "Representatives",
      fields: [
        { key: "representatives.legal_rep.name", label: "Nguoi dai dien phap ly" },
        { key: "representatives.legal_rep.position", label: "Chuc vu" },
        { key: "representatives.contact_person.name", label: "Nguoi lien he" },
        { key: "representatives.contact_person.email", label: "Email lien he" },
        { key: "representatives.contact_person.phone", label: "Dien thoai lien he" },
      ],
    },
    {
      title: "R&D profile",
      fields: [
        { key: "rd_profile.rd_focus_directions", label: "Huong R&D", kind: "array", fields: [{ key: "name", label: "Ten huong" }] },
        { key: "rd_profile.technology_needs", label: "Nhu cau cong nghe", kind: "array", description: "Nhung van de cong nghe doanh nghiep can chuyen gia/project ho tro giai quyet.", fields: [
          { key: "need", label: "Nhu cau", placeholder: "Vi du: du bao loi thiet bi, truy xuat du lieu san xuat" },
          { key: "required_skill", label: "Ky nang can", placeholder: "Vi du: predictive maintenance, IoT, computer vision" },
          { key: "proficiency_level", label: "Muc do", kind: "select", options: proficiencyOptions },
        ] },
        { key: "rd_profile.desired_TRL", label: "TRL mong muon", kind: "number" },
        { key: "rd_profile.rd_capacity.research_staff", label: "Nhan su R&D", kind: "number" },
        { key: "rd_profile.rd_capacity.labs", label: "Phong lab", kind: "array", fields: [{ key: "name", label: "Ten lab" }] },
        { key: "rd_profile.rd_capacity.equipment", label: "Thiet bi", kind: "array", fields: [{ key: "name", label: "Ten thiet bi" }] },
      ],
    },
    {
      title: "Outputs, investment va relations",
      fields: [
        { key: "investment_and_markets.innovation_index", label: "Innovation index", kind: "number" },
        { key: "investment_and_markets.investment_history", label: "Lich su dau tu", kind: "array", fields: [
          { key: "source", label: "Nguon" },
          { key: "amount", label: "So tien", kind: "number" },
          { key: "purpose", label: "Muc dich" },
        ] },
        { key: "outputs_and_transfers.commercialized_assets", label: "Tai san da thuong mai hoa", kind: "array", fields: [
          { key: "product", label: "San pham" },
          { key: "year", label: "Nam", kind: "number" },
          { key: "revenue_estimate", label: "Doanh thu uoc tinh", kind: "number" },
        ] },
        { key: "outputs_and_transfers.patent_outputs", label: "Bang sang che", kind: "array", fields: [
          { key: "type", label: "Loai" },
          { key: "patent_id", label: "Patent ID" },
          { key: "status", label: "Trang thai", kind: "select", options: statusOptions },
        ] },
        { key: "relations.rd_projects", label: "Project R&D", kind: "array", fields: [
          { key: "project_id", label: "Project ID" },
          { key: "role", label: "Vai tro" },
          { key: "status", label: "Trang thai", kind: "select", options: statusOptions },
        ] },
        { key: "relations.worked_experts", label: "Chuyen gia da hop tac", kind: "array", fields: [
          { key: "expert_id", label: "Expert ID" },
          { key: "role", label: "Vai tro" },
          { key: "period", label: "Thoi gian" },
        ] },
      ],
    },
  ],
  funder: [
    {
      title: "Basic info va representatives",
      fields: [
        { key: "basic_info.type", label: "Loai nha tai tro", kind: "select", options: fundingTypeOptions },
        { key: "basic_info.budget_capacity", label: "Nang luc ngan sach" },
        { key: "representatives", label: "Dai dien", kind: "array", fields: [
          { key: "name", label: "Ten" },
          { key: "position", label: "Chuc vu" },
          { key: "email", label: "Email" },
          { key: "phone", label: "Dien thoai" },
        ] },
      ],
    },
    {
      title: "Funding strategy",
      fields: [
        { key: "funding_strategy.funding_directions", label: "Huong tai tro", kind: "array", description: "Cac huong nghien cuu/doi moi sang tao ma quy uu tien cap von.", fields: [{ key: "name", label: "Ten huong", placeholder: "Vi du: AI trong y te, Nang luong tai tao" }] },
        { key: "funding_strategy.focus_regions", label: "Vung uu tien", kind: "array", fields: [{ key: "name", label: "Ten vung" }] },
        { key: "funding_strategy.focus_sectors", label: "Linh vuc uu tien", kind: "array", fields: [{ key: "name", label: "Ten linh vuc" }] },
        { key: "funding_strategy.trl_range_focus.min", label: "TRL toi thieu", kind: "number" },
        { key: "funding_strategy.trl_range_focus.max", label: "TRL toi da", kind: "number" },
        { key: "funding_strategy.typical_grant_size", label: "Muc tai tro dien hinh" },
        { key: "funding_strategy.eligibility_criteria", label: "Tieu chi hop le", kind: "textarea" },
        { key: "funding_strategy.application_process", label: "Quy trinh nop ho so", kind: "textarea" },
      ],
    },
    {
      title: "Programs, history va impact",
      fields: [
        { key: "programs", label: "Chuong trinh tai tro", kind: "array", fields: [
          { key: "program_id", label: "Program ID" },
          { key: "title", label: "Ten chuong trinh" },
          { key: "application_window", label: "Thoi gian nop" },
          { key: "max_amount", label: "Muc toi da", kind: "number" },
          { key: "currency", label: "Tien te" },
        ] },
        { key: "funding_history.funded_projects", label: "Project da tai tro", kind: "array", fields: [
          { key: "project_id", label: "Project ID" },
          { key: "title", label: "Ten project" },
          { key: "grant_amount", label: "So tien", kind: "number" },
          { key: "year", label: "Nam", kind: "number" },
          { key: "status", label: "Trang thai", kind: "select", options: statusOptions },
        ] },
        { key: "funding_history.annual_grant_history", label: "Grant theo nam", kind: "array", fields: [
          { key: "year", label: "Nam", kind: "number" },
          { key: "total_amount", label: "Tong tien", kind: "number" },
          { key: "recipients", label: "So ben nhan", kind: "number" },
        ] },
        { key: "impact_metrics.projects_success_rate", label: "Ty le project thanh cong", kind: "number" },
        { key: "impact_metrics.commercialization_rate", label: "Ty le thuong mai hoa", kind: "number" },
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
      setMessage(err instanceof Error ? err.message : "Luu profile that bai");
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
                Them muc
              </Button>
            ) : null}
          </div>
          <div className="space-y-3">
            {items.length === 0 ? (
              <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">Chua co du lieu.</div>
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
              <h1 className="text-3xl font-bold tracking-tight">Trang ca nhan</h1>
              <p className="text-muted-foreground">Thong tin co ban, profile chi tiet va du lieu dung cho recommendation.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setShowDetails((value) => !value)}>
              <Eye className="mr-2 h-4 w-4" />
              {showDetails ? "An chi tiet" : "Xem thong tin chi tiet"}
            </Button>
            {isEditing ? (
              <Button type="button" variant="outline" onClick={cancelEdit}>
                <X className="mr-2 h-4 w-4" />
                Huy chinh sua
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
                Chinh sua
              </Button>
            )}
          </div>
        </header>

        <section className="profile-reveal mb-6 rounded-md border bg-card p-5 shadow-sm">
          <div className="grid gap-5 md:grid-cols-[1.4fr_1fr_1fr]">
            <div>
              <div className="text-sm text-muted-foreground">{roleLabel(profile.role)}</div>
              <div className="mt-1 text-2xl font-bold">{profile.full_name || "Chua cap nhat ten"}</div>
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
              <div className="text-xs font-semibold uppercase text-muted-foreground">To chuc</div>
              <div className="mt-2 font-medium">{profile.organization || "Chua cap nhat"}</div>
              <div className="mt-4 text-xs font-semibold uppercase text-muted-foreground">Dia diem</div>
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
            Ho so cua ban da duoc dua vao Knowledge Graph o trang thai chua xac thuc. Ban co the dung de nhan goi y ca nhan,
            nhung ket qua co the thay doi sau khi duoc duyet.
          </p>
        ) : null}

        {profile.linked_entity?.match_status === "matched_existing" ? (
          <p className="profile-reveal mb-6 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
            He thong da tim thay ho so co san khop voi thong tin dang ky cua ban va da lien ket tai khoan voi entity nay.
            Du lieu nay duoc xem la entity co san cua he thong, nen co the dung de recommendation voi trust weight day du.
          </p>
        ) : null}

        {profile.linked_entity?.kg_sync_status === "merge_required" &&
        (profile.linked_entity?.duplicate_candidates?.length ?? 0) > 0 ? (
          <p className="profile-reveal mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            He thong phat hien ho so co kha nang trung voi data da co. Can admin review/merge truoc khi public rong rai.
          </p>
        ) : null}

        {showDetails || isEditing ? (
          <section className="profile-detail rounded-md border bg-card p-6 shadow-sm">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-2xl font-bold">Thong tin chi tiet</h2>
                <p className="text-sm text-muted-foreground">
                  {isEditing
                    ? "Cac truong deu khong bat buoc. Ban co the bo sung dan de he thong goi y tot hon."
                    : "Bam Chinh sua neu muon cap nhat cac thong tin nay."}
                </p>
              </div>
              {isEditing ? <Badge className="rounded-md">Dang chinh sua</Badge> : null}
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="profile-detail-reveal space-y-2">
                <Label>Ho ten / ten don vi</Label>
                <Input disabled={!isEditing} value={profile.full_name} onChange={(e) => updateProfile({ full_name: e.target.value })} />
              </div>
              <div className="profile-detail-reveal space-y-2">
                <Label>Username</Label>
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

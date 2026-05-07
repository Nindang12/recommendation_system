"""
Script chạy PGPR theo từng bước hoặc chạy toàn bộ.
Dùng: python run_pgpr.py --step 1 | --step 2 | --step 3 --project_id PRJ_0001 | --all
"""
import argparse
import os
import sys


def run_step1(data_dir: str = "pgpr_data", emb_dim: int = 64) -> None:
    """Bước 1: Export KG từ Neo4j, lưu vocab + triples, train TransE."""
    from pgpr_kg import build_kg_from_neo4j
    print("Bước 1: Chuẩn bị KG và embedding...")
    build_kg_from_neo4j(data_dir=data_dir, train_emb=True, emb_dim=emb_dim)
    print("Bước 1 xong. Đã tạo:", data_dir, "-> vocab.json, triples.txt, entity_emb.npy, relation_emb.npy")


def run_step2(
    data_dir: str = "pgpr_data",
    n_epoch: int = 50,
    save_path: str = None,
    n_positive: int = 200,
    n_negative: int = 200,
) -> None:
    """Bước 2: Train policy REINFORCE."""
    from pgpr_train import train_pgpr
    save_path = save_path or os.path.join(data_dir, "policy.pt")
    print("Bước 2: Train policy (REINFORCE)...")
    train_pgpr(
        data_dir=data_dir,
        n_epoch=n_epoch,
        save_path=save_path,
        n_positive=n_positive,
        n_negative=n_negative,
    )
    print("Bước 2 xong. Đã tạo:", save_path)


def run_step3(project_id: str = "PRJ_0001", data_dir: str = "pgpr_data", limit: int = 5) -> None:
    """Bước 3: Gợi ý chuyên gia cho project (PGPR hoặc heuristic)."""
    from pgpr_recommendation import PGPRRecommender, print_pgpr_recommendations
    print("Bước 3: Recommendation cho project", project_id, "...")
    engine = PGPRRecommender(max_path_length=5, data_dir=data_dir)
    use_policy = engine.policy is not None
    print("Dùng policy-guided path:" if use_policy else "Dùng heuristic (chưa có policy).")
    recs = engine.recommend_experts_for_project_pgpr(project_id, limit=limit, use_policy=use_policy)
    print_pgpr_recommendations(recs, f"Gợi ý chuyên gia cho {project_id}")
    engine.close()
    print("Bước 3 xong.")


def main():
    parser = argparse.ArgumentParser(description="Chạy PGPR: step 1 (KG+embedding), step 2 (train policy), step 3 (recommendation)")
    parser.add_argument("--step", type=int, choices=[1, 2, 3], help="Chỉ chạy bước 1, 2 hoặc 3")
    parser.add_argument("--all", action="store_true", help="Chạy bước 1 rồi bước 2 (không chạy 3)")
    parser.add_argument("--data_dir", default="pgpr_data", help="Thư mục dữ liệu PGPR")
    parser.add_argument("--project_id", default="PRJ_0001", help="Project ID cho bước 3")
    parser.add_argument("--n_epoch", type=int, default=50, help="Số epoch train policy (bước 2)")
    parser.add_argument("--emb_dim", type=int, default=64, help="Embedding dimension (bước 1)")
    parser.add_argument("--n_positive", type=int, default=200)
    parser.add_argument("--n_negative", type=int, default=200)
    parser.add_argument("--limit", type=int, default=5, help="Số expert gợi ý (bước 3)")
    args = parser.parse_args()

    if args.all:
        run_step1(data_dir=args.data_dir, emb_dim=args.emb_dim)
        run_step2(data_dir=args.data_dir, n_epoch=args.n_epoch, n_positive=args.n_positive, n_negative=args.n_negative)
        print("Đã chạy bước 1 và 2. Để gợi ý chuyên gia, chạy: python run_pgpr.py --step 3 --project_id PRJ_0001")
        return

    if args.step == 1:
        run_step1(data_dir=args.data_dir, emb_dim=args.emb_dim)
    elif args.step == 2:
        run_step2(data_dir=args.data_dir, n_epoch=args.n_epoch, n_positive=args.n_positive, n_negative=args.n_negative)
    elif args.step == 3:
        run_step3(project_id=args.project_id, data_dir=args.data_dir, limit=args.limit)
    else:
        parser.print_help()
        print("\nVí dụ:")
        print("  python run_pgpr.py --step 1")
        print("  python run_pgpr.py --step 2 --n_epoch 30")
        print("  python run_pgpr.py --step 3 --project_id PRJ_0004")
        print("  python run_pgpr.py --all")


if __name__ == "__main__":
    main()

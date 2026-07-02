.PHONY: dev dev-rebuild stop logs backup clean qa qa-backend qa-frontend container-inventory

# 启动开发环境
dev:
	docker compose -f docker-compose.dev.yml up -d --build

# 重建并启动（强制重新构建镜像）
dev-rebuild:
	docker compose -f docker-compose.dev.yml up -d --build --force-recreate

# 停止开发环境
stop:
	docker compose -f docker-compose.dev.yml down

# 查看后端日志
logs:
	docker compose -f docker-compose.dev.yml logs -f backend

# 备份数据库
backup:
	@mkdir -p backups
	@cp data/dev.db backups/dev_$$(date +%Y%m%d_%H%M%S).db 2>/dev/null || echo "数据库文件不存在，跳过备份"

# 清理所有容器、镜像和数据
clean:
	docker compose -f docker-compose.dev.yml down -v --rmi local
	rm -rf data/dev.db logs/app.log

# === QA 自动化测试 ===
# 一键跑完整测试套件：后端 pytest + 前端 build
qa: qa-backend qa-frontend
	@echo ""
	@echo "==================================="
	@echo "✅ QA 全部通过"
	@echo "==================================="

# 后端测试（pytest）
qa-backend:
	@echo ">>> 跑后端测试 (pytest)..."
	docker compose -f docker-compose.dev.yml run --rm qa-backend

# 前端测试（vite build）
# 注：Vite build 遇到错误仍会 exit 0，所以要检查输出文本里是否包含 error
# 用容器跑保证环境一致
qa-frontend:
	@echo ">>> 跑前端 build 检查..."
	@docker compose -f docker-compose.dev.yml run --rm qa-frontend 2>&1 | tee /tmp/qa-frontend.log > /dev/null
	@if grep -qE "(Error when|is not exported|is not defined|Cannot find module|Failed to resolve|not found|FAIL)" /tmp/qa-frontend.log; then \
		echo "❌ 前端 build 失败：发现错误信息"; \
		cat /tmp/qa-frontend.log | grep -E "(Error|FAIL|not found|not exported|not defined)"; \
		exit 1; \
	else \
		echo "✅ 前端 build 通过"; \
	fi

# === 容器盘点 (v24-container-cleanup) ===
# 生成 docs/CONTAINER-INVENTORY.md 基线
container-inventory:
	@./scripts/container-inventory.sh

.PHONY: dev dev-rebuild stop logs backup clean

# 启动开发环境
dev:
	docker-compose -f docker-compose.dev.yml up -d --build

# 重建并启动（强制重新构建镜像）
dev-rebuild:
	docker-compose -f docker-compose.dev.yml up -d --build --force-recreate

# 停止开发环境
stop:
	docker-compose -f docker-compose.dev.yml down

# 查看后端日志
logs:
	docker-compose -f docker-compose.dev.yml logs -f backend

# 备份数据库
backup:
	@mkdir -p backups
	@cp data/dev.db backups/dev_$$(date +%Y%m%d_%H%M%S).db 2>/dev/null || echo "数据库文件不存在，跳过备份"

# 清理所有容器、镜像和数据
clean:
	docker-compose -f docker-compose.dev.yml down -v --rmi local
	rm -rf data/dev.db logs/app.log

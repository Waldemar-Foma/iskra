// static/script.js - Обновленный
document.addEventListener('DOMContentLoaded', function() {
    initHamburgerMenu();
    initFlashMessages();
    initBackToTop();
    initLiveFeed();
    initWorldUpdates();
    initMobileNav();
    initSystemTime();
});

// Гамбургер меню
function initHamburgerMenu() {
    const hamburger = document.getElementById('hamburgerBtn');
    const menu = document.getElementById('menu');
    const menuClose = document.getElementById('menuClose');
    const overlay = document.getElementById('menuOverlay');
    
    if (!hamburger || !menu) return;
    
    function toggleMenu(show) {
        menu.classList.toggle('active', show);
        if (overlay) overlay.classList.toggle('active', show);
        document.body.style.overflow = show ? 'hidden' : '';
    }
    
    hamburger.addEventListener('click', () => toggleMenu(true));
    
    if (menuClose) {
        menuClose.addEventListener('click', () => toggleMenu(false));
    }
    
    if (overlay) {
        overlay.addEventListener('click', () => toggleMenu(false));
    }
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && menu.classList.contains('active')) {
            toggleMenu(false);
        }
    });
    
    menu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => toggleMenu(false));
    });
}

// Flash сообщения
function initFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-message');
    
    flashMessages.forEach(message => {
        // Авто-скрытие через 5 секунд
        setTimeout(() => {
            hideFlashMessage(message);
        }, 5000);
        
        // Кнопка закрытия
        const closeBtn = message.querySelector('.flash-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => hideFlashMessage(message));
        }
    });
}

function hideFlashMessage(message) {
    message.style.animation = 'slideInRight 0.3s reverse';
    setTimeout(() => {
        message.remove();
    }, 300);
}

// Кнопка наверх
function initBackToTop() {
    const backToTop = document.getElementById('backToTop');
    if (!backToTop) return;
    
    window.addEventListener('scroll', () => {
        if (window.scrollY > 300) {
            backToTop.classList.add('visible');
        } else {
            backToTop.classList.remove('visible');
        }
    });
    
    backToTop.addEventListener('click', () => {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

// Live Feed
function initLiveFeed() {
    const feedContainer = document.getElementById('liveFeed');
    if (!feedContainer) return;
    
    function fetchEvents() {
        fetch('/api/events/latest')
            .then(response => response.json())
            .then(events => {
                feedContainer.innerHTML = '';
                events.forEach(event => {
                    const item = document.createElement('div');
                    item.className = 'feed-item';
                    
                    const time = new Date(event.timestamp);
                    const timeStr = time.toLocaleTimeString('ru-RU', { 
                        hour: '2-digit', 
                        minute: '2-digit',
                        second: '2-digit' 
                    });
                    
                    item.innerHTML = `
                        <span class="feed-item-time">${timeStr}</span>
                        <span class="feed-item-text">${event.text}</span>
                    `;
                    feedContainer.appendChild(item);
                });
            })
            .catch(console.error);
    }
    
    fetchEvents();
    setInterval(fetchEvents, 5000);
}

// Обновление статусов мира
function initWorldUpdates() {
    function updateWorldStats() {
        fetch('/api/world-state')
            .then(response => response.json())
            .then(data => {
                // Обновление счетчика агентов
                const agentCount = document.getElementById('agentCount');
                if (agentCount && data.agents) {
                    agentCount.textContent = data.agents.length;
                }
                
                // Обновление цикла мира
                const worldCycle = document.getElementById('worldCycle');
                if (worldCycle) {
                    worldCycle.textContent = `Цикл: ${data.cycle}`;
                }
                
                // Обновление статистики на главной
                const totalAgents = document.getElementById('totalAgents');
                if (totalAgents && data.agents) {
                    totalAgents.textContent = data.agents.length;
                }
                
                const worldComplexity = document.getElementById('worldComplexity');
                if (worldComplexity) {
                    worldComplexity.textContent = data.complexity.toFixed(2);
                }
                
                // Обновление количества взаимодействий
                const activeInteractions = document.getElementById('activeInteractions');
                if (activeInteractions) {
                    fetch('/api/graph-data')
                        .then(r => r.json())
                        .then(graphData => {
                            activeInteractions.textContent = graphData.links.length;
                        })
                        .catch(console.error);
                }
            })
            .catch(console.error);
    }
    
    updateWorldStats();
    setInterval(updateWorldStats, 3000);
}

// Мобильная навигация
function initMobileNav() {
    const currentPath = window.location.pathname;
    const navItems = document.querySelectorAll('.mobile-nav-item');
    
    navItems.forEach(item => {
        const href = item.getAttribute('href');
        if (href === currentPath || 
            (currentPath === '/' && href === '/') ||
            (currentPath.startsWith('/profile') && href === '/profile')) {
            item.classList.add('active');
        }
    });
}

// Системное время
function initSystemTime() {
    const timeEl = document.getElementById('systemTime');
    if (!timeEl) return;
    
    function updateTime() {
        const now = new Date();
        timeEl.textContent = now.toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    updateTime();
    setInterval(updateTime, 1000);
}

// Граф (если есть на странице)
if (document.getElementById('agentGraph')) {
    initGraph();
}

function initGraph() {
    const canvas = document.getElementById('agentGraph');
    const ctx = canvas.getContext('2d');
    
    function drawGraph() {
        fetch('/api/graph-data')
            .then(response => response.json())
            .then(data => {
                const nodes = data.nodes;
                const links = data.links;
                const centerX = canvas.width / 2;
                const centerY = canvas.height / 2;
                
                // Позиции узлов (простое круговое расположение)
                const positions = {};
                if (nodes && nodes.length > 0) {
                    nodes.forEach((node, i) => {
                        const angle = (i / nodes.length) * 2 * Math.PI;
                        positions[node.id] = {
                            x: centerX + 200 * Math.cos(angle),
                            y: centerY + 200 * Math.sin(angle)
                        };
                    });
                    
                    // Рисуем связи
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    
                    if (links && links.length > 0) {
                        links.forEach(link => {
                            const source = positions[link.source];
                            const target = positions[link.target];
                            
                            if (source && target) {
                                ctx.beginPath();
                                ctx.moveTo(source.x, source.y);
                                ctx.lineTo(target.x, target.y);
                                ctx.strokeStyle = link.value > 0 ? 
                                    'rgba(2, 124, 125, 0.5)' : 
                                    'rgba(230, 0, 106, 0.5)';
                                ctx.lineWidth = Math.abs(link.value) * 3;
                                ctx.stroke();
                            }
                        });
                    }
                    
                    // Рисуем узлы
                    nodes.forEach(node => {
                        const pos = positions[node.id];
                        if (pos) {
                            // Тень
                            ctx.shadowColor = 'rgba(230, 0, 106, 0.3)';
                            ctx.shadowBlur = 15;
                            
                            // Круг
                            ctx.beginPath();
                            ctx.arc(pos.x, pos.y, 15 + node.energy * 10, 0, 2 * Math.PI);
                            
                            if (node.type === 'Базовая') {
                                ctx.fillStyle = 'rgba(2, 124, 125, 0.8)';
                            } else if (node.type === 'Продвинутая') {
                                ctx.fillStyle = 'rgba(230, 0, 106, 0.8)';
                            } else {
                                const gradient = ctx.createLinearGradient(pos.x-15, pos.y-15, pos.x+15, pos.y+15);
                                gradient.addColorStop(0, '#027C7D');
                                gradient.addColorStop(1, '#E6006A');
                                ctx.fillStyle = gradient;
                            }
                            
                            ctx.fill();
                            ctx.strokeStyle = '#fff';
                            ctx.lineWidth = 2;
                            ctx.stroke();
                            
                            // Сброс тени
                            ctx.shadowBlur = 0;
                            
                            // Имя
                            ctx.fillStyle = '#fff';
                            ctx.font = 'bold 12px Inter, sans-serif';
                            ctx.textAlign = 'center';
                            ctx.fillText(node.id, pos.x, pos.y - 25);
                            
                            // Энергия
                            ctx.fillStyle = '#b0b0b0';
                            ctx.font = '10px Inter, sans-serif';
                            ctx.fillText(`⚡${Math.round(node.energy * 100)}%`, pos.x, pos.y + 30);
                        }
                    });
                }
            })
            .catch(console.error);
    }
    
    drawGraph();
    setInterval(drawGraph, 5000);
}
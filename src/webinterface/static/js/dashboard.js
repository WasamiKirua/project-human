/**
 * Project Human Redis - Dashboard JavaScript
 * Real-time updates and interactivity
 */

class Dashboard {
    constructor() {
        this.websocket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.theme = localStorage.getItem('theme') || 'light';
        
        this.init();
    }

    init() {
        this.initTheme();
        this.initWebSocket();
        this.bindEventListeners();
        this.startPeriodicUpdates();
        
        console.log('Dashboard initialized');
    }

    initTheme() {
        // Set initial theme
        document.documentElement.setAttribute('data-theme', this.theme);
        
        // Update theme toggle button
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.innerHTML = this.theme === 'light' ? '🌙' : '☀️';
        }
    }

    toggleTheme() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', this.theme);
        localStorage.setItem('theme', this.theme);
        
        // Update toggle button
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.innerHTML = this.theme === 'light' ? '🌙' : '☀️';
        }
    }

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.reconnectAttempts = 0;
                this.showConnectionStatus(true);
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            
            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.showConnectionStatus(false);
                this.attemptReconnect();
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.showConnectionStatus(false);
            };
            
        } catch (error) {
            console.error('Error initializing WebSocket:', error);
            this.showConnectionStatus(false);
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            
            setTimeout(() => {
                this.initWebSocket();
            }, this.reconnectDelay);
        } else {
            console.log('Max reconnection attempts reached');
            this.showError('Connection lost. Please refresh the page.');
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'initial_status':
            case 'status_update':
                this.updateServiceStatus(data.data.services);
                this.updateSystemInfo(data.data.system);
                break;
            case 'pong':
                // Handle ping/pong for connection health
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    updateServiceStatus(services) {
        // Update infrastructure services
        if (services.infrastructure) {
            for (const [service, status] of Object.entries(services.infrastructure)) {
                this.updateServiceCard(service, status, 'infrastructure');
            }
        }
        
        // Update components
        if (services.components) {
            for (const [component, status] of Object.entries(services.components)) {
                this.updateServiceCard(component, status, 'components');
            }
        }
    }

    updateSystemInfo(systemInfo) {
        if (systemInfo.error) {
            console.error('System info error:', systemInfo.error);
            return;
        }
        
        // Note: System info elements removed from template
        // This function exists to prevent errors but doesn't update anything
    }

    updateServiceCard(serviceName, status, category) {
        const cardId = `${serviceName}-card`;
        const statusElement = document.getElementById(`${serviceName}-status`);
        const messageElement = document.getElementById(`${serviceName}-message`);
        const badgeElement = document.getElementById(`${serviceName}-badge`);
        
        if (statusElement) {
            statusElement.className = `status-${status.status}`;
            statusElement.textContent = status.status.toUpperCase();
        }
        
        if (messageElement) {
            messageElement.textContent = status.message;
        }
        
        if (badgeElement) {
            badgeElement.className = `badge badge-kawaii badge-${status.status}`;
            badgeElement.textContent = status.status.toUpperCase();
        }
        
        // Update card border color based on status
        const card = document.getElementById(cardId);
        if (card) {
            card.classList.remove('border-success', 'border-danger', 'border-warning');
            if (status.status === 'running') {
                card.classList.add('border-success');
            } else if (status.status === 'error') {
                card.classList.add('border-danger');
            } else {
                card.classList.add('border-warning');
            }
        }
    }

    bindEventListeners() {
        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
        }
        
        // Service control buttons
        document.addEventListener('click', async (event) => {
            if (event.target.matches('[data-action]')) {
                await this.handleServiceAction(event.target);
            }
        });
        
        // Refresh button
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.requestStatusUpdate());
        }
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        notification.style.cssText = 'top: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; min-width: 300px;';
        
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    showConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (statusElement) {
            statusElement.className = connected ? 'badge badge-success' : 'badge badge-danger';
            statusElement.textContent = connected ? 'Connected' : 'Disconnected';
        }
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showError(message) {
        this.showNotification(message, 'danger');
    }

    requestStatusUpdate() {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({ type: 'request_status' }));
            this.showSuccess('Status refresh requested');
        } else {
            this.showError('WebSocket not connected');
        }
    }

    requestLogs(component, lines = 50) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: 'request_logs',
                component: component,
                lines: lines
            }));
        }
    }

    startPeriodicUpdates() {
        // Send ping every 30 seconds to keep connection alive
        setInterval(() => {
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                this.websocket.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);
    }

    async handleServiceAction(button) {
        const service = button.dataset.service;
        const action = button.dataset.action;
        
        if (!service || !action) return;
        
        // Disable button during action
        button.disabled = true;
        const originalText = button.textContent;
        button.textContent = 'Processing...';
        
        try {
            const response = await fetch(`/api/services/${service}/${action}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccess(`${service} ${action} successful: ${result.message}`);
                // Request immediate status update
                this.requestStatusUpdate();
            } else {
                this.showError(`${service} ${action} failed: ${result.message}`);
            }
        } catch (error) {
            console.error('Service action error:', error);
            this.showError(`Failed to ${action} ${service}: ${error.message}`);
        } finally {
            // Re-enable button
            button.disabled = false;
            button.textContent = originalText;
        }
    }

    async handleBulkAction(action, buttonElement = null) {
        // If no button provided, try to find it by data attribute (legacy)
        const button = buttonElement || document.querySelector(`[data-bulk-action="${action}"]`);
        if (button) {
            button.disabled = true;
            const originalText = button.textContent;
            button.textContent = 'Processing...';
            
            try {
                const response = await fetch(`/api/services/${action}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const result = await response.json();
                console.log('Bulk action result:', result);
                
                this.showSuccess(`Bulk action ${action} completed`);
                this.requestStatusUpdate();
            } catch (error) {
                console.error('Bulk action error:', error);
                this.showError(`Bulk action failed: ${error.message}`);
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        } else {
            // If no button found, still try to execute the action
            try {
                const response = await fetch(`/api/services/${action}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const result = await response.json();
                console.log('Bulk action result:', result);
                
                this.showSuccess(`Bulk action ${action} completed`);
                this.requestStatusUpdate();
            } catch (error) {
                console.error('Bulk action error:', error);
                this.showError(`Bulk action failed: ${error.message}`);
            }
        }
    }
}

// Global functions for template use
window.startService = function(service) {
    if (window.dashboard) {
        window.dashboard.handleServiceAction({
            dataset: { service: service, action: 'start' },
            disabled: false,
            textContent: 'Start'
        });
    }
};

window.stopService = function(service) {
    if (window.dashboard) {
        window.dashboard.handleServiceAction({
            dataset: { service: service, action: 'stop' },
            disabled: false,
            textContent: 'Stop'
        });
    }
};

window.handleBulkAction = function(action, buttonElement = null) {
    if (window.dashboard) {
        window.dashboard.handleBulkAction(action, buttonElement);
    }
};

window.requestLogs = function(component) {
    if (window.dashboard) {
        window.dashboard.requestLogs(component);
    }
};

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.dashboard = new Dashboard();
    console.log('Dashboard ready');
});

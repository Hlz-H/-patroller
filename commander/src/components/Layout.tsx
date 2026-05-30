import React, { useEffect } from 'react';
import { Layout as AntLayout, Menu, Badge, Typography, Space, Button, theme } from 'antd';
import {
  DashboardOutlined,
  AppstoreOutlined,
  UsbOutlined,
  AlertOutlined,
  SettingOutlined,
  ReloadOutlined,
  WifiOutlined,
  ApiOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useStore } from '../store';

const { Header, Sider, Content } = AntLayout;
const { Text } = Typography;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/processes', icon: <AppstoreOutlined />, label: '进程管理' },
  { key: '/usb', icon: <UsbOutlined />, label: 'USB 管理' },
  { key: '/sandbox', icon: <SafetyOutlined />, label: '沙箱管理' },
  { key: '/alerts', icon: <AlertOutlined />, label: '告警记录' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
];

const Layout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();
  const {
    isConnected,
    status,
    unacknowledgedCount,
    connectWebSocket,
    disconnectWebSocket,
    fetchStatus,
  } = useStore();

  useEffect(() => {
    connectWebSocket();
    fetchStatus();
    const timer = setInterval(fetchStatus, 5000);
    return () => {
      disconnectWebSocket();
      clearInterval(timer);
    };
  }, []);

  const handleRefresh = () => {
    fetchStatus();
  };

  const selectedKey = '/' + location.pathname.split('/')[1] || '/';

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        style={{
          background: token.colorBgContainer,
          borderRight: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Space>
            <ApiOutlined style={{ fontSize: 22, color: token.colorPrimary }} />
            <Text strong style={{ fontSize: 16, color: token.colorText }}>
              巡查者
            </Text>
          </Space>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => navigate(key)}
          items={menuItems.map((item) => {
            if (item.key === '/alerts' && unacknowledgedCount > 0) {
              return {
                ...item,
                label: (
                  <Space>
                    {item.label}
                    <Badge count={unacknowledgedCount} size="small" />
                  </Space>
                ),
              };
            }
            return item;
          })}
          style={{ borderRight: 0, marginTop: 8 }}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            height: 64,
          }}
        >
          <Space size="large">
            <Space>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: isConnected ? '#52c41a' : '#ff4d4f',
                  display: 'inline-block',
                  boxShadow: isConnected
                    ? '0 0 6px #52c41a'
                    : '0 0 6px #ff4d4f',
                }}
              />
              <Text style={{ fontSize: 13 }}>
                {isConnected ? '已连接' : '未连接'}
              </Text>
            </Space>
            {status && (
              <Text type="secondary" style={{ fontSize: 13 }}>
                代理: {status.agent_name} v{status.version}
              </Text>
            )}
          </Space>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={handleRefresh}
            >
              刷新
            </Button>
          </Space>
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: token.colorBgContainer,
            borderRadius: token.borderRadiusLG,
            minHeight: 280,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;

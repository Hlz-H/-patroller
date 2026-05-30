import React, { useEffect, useState } from 'react';
import {
  Card,
  Typography,
  Switch,
  Space,
  Button,
  Tag,
  Input,
  message,
  Spin,
  Divider,
} from 'antd';
import {
  SettingOutlined,
  SaveOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useStore } from '../store';

const { Title, Text } = Typography;

const Settings: React.FC = () => {
  const { config, fetchConfig, fetchStatus, saveConfig, loading } = useStore();
  const [localConfig, setLocalConfig] = useState(config);
  const [newWhitelist, setNewWhitelist] = useState('');
  const [newBlacklist, setNewBlacklist] = useState('');
  const [newUSBBlock, setNewUSBBlock] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, []);

  useEffect(() => {
    if (config) {
      setLocalConfig({ ...config });
    }
  }, [config]);

  if (!localConfig || loading.config) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}>
          <Text type="secondary">正在加载设置...</Text>
        </div>
      </div>
    );
  }

  const handleToggle = (key: keyof typeof localConfig) => {
    if (typeof localConfig[key] === 'boolean') {
      setLocalConfig({ ...localConfig, [key]: !localConfig[key] });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    const success = await saveConfig(localConfig);
    if (success) {
      message.success('设置已保存');
      fetchStatus();
    } else {
      message.error('保存失败，请检查 Agent 连接');
    }
    setSaving(false);
  };

  const addWhitelist = () => {
    if (!newWhitelist.trim()) return;
    setLocalConfig({
      ...localConfig,
      process_whitelist: [...localConfig.process_whitelist, newWhitelist.trim()],
    });
    setNewWhitelist('');
  };

  const addBlacklist = () => {
    if (!newBlacklist.trim()) return;
    setLocalConfig({
      ...localConfig,
      process_blacklist: [...localConfig.process_blacklist, newBlacklist.trim()],
    });
    setNewBlacklist('');
  };

  const addUSBBlock = () => {
    if (!newUSBBlock.trim()) return;
    const entry = newUSBBlock.trim();
    if (!entry.includes(':')) {
      message.warning('格式应为 VID:PID，例如 0781:5591');
      return;
    }
    setLocalConfig({
      ...localConfig,
      usb_blocklist: [...localConfig.usb_blocklist, entry],
    });
    setNewUSBBlock('');
  };

  const removeFromList = (list: string[], index: number, key: 'process_whitelist' | 'process_blacklist' | 'usb_blocklist') => {
    const newList = [...list];
    newList.splice(index, 1);
    setLocalConfig({ ...localConfig, [key]: newList });
  };

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <SettingOutlined /> 系统设置
      </Title>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Monitor Toggles */}
        <Card title="监控开关" size="small">
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <Text>进程监控</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  监控可疑进程行为
                </Text>
              </Space>
              <Switch
                checked={localConfig.monitor_enabled}
                onChange={() => handleToggle('monitor_enabled')}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <Text>USB 监控</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  监控 USB 设备插拔
                </Text>
              </Space>
              <Switch
                checked={localConfig.usb_monitor_enabled}
                onChange={() => handleToggle('usb_monitor_enabled')}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <Text>网络监控</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  监控网络连接异常
                </Text>
              </Space>
              <Switch
                checked={localConfig.network_monitor_enabled}
                onChange={() => handleToggle('network_monitor_enabled')}
              />
            </div>
          </Space>
        </Card>

        {/* Process Whitelist */}
        <Card title="进程白名单" size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <Input
                placeholder="进程名称 (如 explorer.exe)"
                value={newWhitelist}
                onChange={(e) => setNewWhitelist(e.target.value)}
                onPressEnter={addWhitelist}
                style={{ width: 300 }}
              />
              <Button
                type="primary"
                size="small"
                icon={<PlusOutlined />}
                onClick={addWhitelist}
              >
                添加
              </Button>
            </Space>
            <div>
              {localConfig.process_whitelist.length === 0 ? (
                <Text type="secondary">暂无白名单规则</Text>
              ) : (
                localConfig.process_whitelist.map((item, idx) => (
                  <Tag
                    key={`wl-${idx}`}
                    closable
                    onClose={() => removeFromList(localConfig.process_whitelist, idx, 'process_whitelist')}
                    color="green"
                    style={{ marginBottom: 8 }}
                  >
                    {item}
                  </Tag>
                ))
              )}
            </div>
          </Space>
        </Card>

        {/* Process Blacklist */}
        <Card title="进程黑名单" size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <Input
                placeholder="进程名称 (如 unknown.exe)"
                value={newBlacklist}
                onChange={(e) => setNewBlacklist(e.target.value)}
                onPressEnter={addBlacklist}
                style={{ width: 300 }}
              />
              <Button
                danger
                size="small"
                icon={<PlusOutlined />}
                onClick={addBlacklist}
              >
                添加
              </Button>
            </Space>
            <div>
              {localConfig.process_blacklist.length === 0 ? (
                <Text type="secondary">暂无黑名单规则</Text>
              ) : (
                localConfig.process_blacklist.map((item, idx) => (
                  <Tag
                    key={`bl-${idx}`}
                    closable
                    onClose={() => removeFromList(localConfig.process_blacklist, idx, 'process_blacklist')}
                    color="red"
                    style={{ marginBottom: 8 }}
                  >
                    {item}
                  </Tag>
                ))
              )}
            </div>
          </Space>
        </Card>

        {/* USB Blocklist */}
        <Card title="USB 阻止列表" size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <Input
                placeholder="VID:PID (如 0781:5591)"
                value={newUSBBlock}
                onChange={(e) => setNewUSBBlock(e.target.value)}
                onPressEnter={addUSBBlock}
                style={{ width: 300 }}
              />
              <Button
                danger
                size="small"
                icon={<PlusOutlined />}
                onClick={addUSBBlock}
              >
                添加
              </Button>
            </Space>
            <div>
              {localConfig.usb_blocklist.length === 0 ? (
                <Text type="secondary">暂无阻止规则</Text>
              ) : (
                localConfig.usb_blocklist.map((item, idx) => (
                  <Tag
                    key={`ub-${idx}`}
                    closable
                    onClose={() => removeFromList(localConfig.usb_blocklist, idx, 'usb_blocklist')}
                    color="red"
                    style={{ marginBottom: 8 }}
                  >
                    {item}
                  </Tag>
                ))
              )}
            </div>
          </Space>
        </Card>

        <Divider />

        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            size="large"
            icon={<SaveOutlined />}
            onClick={handleSave}
            loading={saving}
          >
            保存设置
          </Button>
        </div>
      </Space>
    </div>
  );
};

export default Settings;

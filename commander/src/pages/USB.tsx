import React, { useEffect, useState } from 'react';
import {
  Card,
  Table,
  Tag,
  Typography,
  Space,
  Button,
  Modal,
  Input,
  message,
  Empty,
} from 'antd';
import {
  UsbOutlined,
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useStore } from '../store';
import type { USBDeviceInfo } from '../types';

const { Title, Text } = Typography;

const statusConfig: Record<string, { color: string; label: string }> = {
  connected: { color: 'green', label: '已连接' },
  disconnected: { color: 'default', label: '已断开' },
  blocked: { color: 'red', label: '已阻止' },
};

const USB: React.FC = () => {
  const { usbDevices, loading, fetchUSB, config, saveConfig } = useStore();
  const [blockModalOpen, setBlockModalOpen] = useState(false);
  const [newBlockVID, setNewBlockVID] = useState('');
  const [newBlockPID, setNewBlockPID] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchUSB();
    const timer = setInterval(fetchUSB, 10000);
    return () => clearInterval(timer);
  }, []);

  const columns: ColumnsType<USBDeviceInfo> = [
    {
      title: '设备名称',
      dataIndex: 'product',
      key: 'product',
      width: 200,
      render: (val: string, record: USBDeviceInfo) => (
        <Space>
          <UsbOutlined />
          <Text>{val || record.manufacturer || '未知设备'}</Text>
        </Space>
      ),
    },
    {
      title: 'VID',
      dataIndex: 'vid',
      key: 'vid',
      width: 100,
    },
    {
      title: 'PID',
      dataIndex: 'pid',
      key: 'pid',
      width: 100,
    },
    {
      title: '序列号',
      dataIndex: 'serial',
      key: 'serial',
      width: 160,
      ellipsis: true,
      render: (val: string) => val || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const cfg = statusConfig[status] || { color: 'default', label: status };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '最后事件',
      dataIndex: 'last_event',
      key: 'last_event',
      width: 180,
      render: (val: string) =>
        val ? new Date(val).toLocaleString('zh-CN') : '-',
    },
  ];

  const handleAddBlock = async () => {
    if (!newBlockVID || !newBlockPID) {
      message.warning('请输入 VID 和 PID');
      return;
    }
    setSaving(true);
    const currentList = config?.usb_blocklist || [];
    const entry = `${newBlockVID}:${newBlockPID}`;
    if (currentList.includes(entry)) {
      message.warning('该设备已在阻止列表中');
      setSaving(false);
      return;
    }
    const success = await saveConfig({
      usb_blocklist: [...currentList, entry],
    });
    if (success) {
      message.success('已添加到 USB 阻止列表');
      setBlockModalOpen(false);
      setNewBlockVID('');
      setNewBlockPID('');
    } else {
      message.error('保存失败');
    }
    setSaving(false);
  };

  const handleRemoveBlock = async (entry: string) => {
    const currentList = config?.usb_blocklist || [];
    const success = await saveConfig({
      usb_blocklist: currentList.filter((e) => e !== entry),
    });
    if (success) {
      message.success('已从阻止列表中移除');
    } else {
      message.error('移除失败');
    }
  };

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <UsbOutlined /> USB 设备管理
      </Title>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card
          title="USB 阻止列表"
          extra={
            <Button
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => setBlockModalOpen(true)}
            >
              添加
            </Button>
          }
          size="small"
        >
          {(!config?.usb_blocklist || config.usb_blocklist.length === 0) ? (
            <Empty description="暂无阻止规则" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            config.usb_blocklist.map((entry) => (
              <Tag
                key={entry}
                closable
                onClose={() => handleRemoveBlock(entry)}
                color="red"
                style={{ marginBottom: 8 }}
              >
                {entry}
              </Tag>
            ))
          )}
        </Card>

        <Card
          title="已连接设备"
          extra={
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={fetchUSB}
              loading={loading.usb}
            >
              刷新
            </Button>
          }
        >
          <Table<USBDeviceInfo>
            dataSource={usbDevices}
            columns={columns}
            rowKey={(record) => `${record.vid}:${record.pid}:${record.serial}`}
            loading={loading.usb}
            size="small"
            scroll={{ x: 850 }}
            pagination={{ pageSize: 20 }}
            locale={{ emptyText: <Empty description="暂无 USB 设备" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
          />
        </Card>
      </Space>

      <Modal
        title="添加 USB 阻止规则"
        open={blockModalOpen}
        onOk={handleAddBlock}
        onCancel={() => {
          setBlockModalOpen(false);
          setNewBlockVID('');
          setNewBlockPID('');
        }}
        confirmLoading={saving}
        okText="添加"
        cancelText="取消"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <div>
            <Text>VID (厂商 ID):</Text>
            <Input
              placeholder="例如: 0781"
              value={newBlockVID}
              onChange={(e) => setNewBlockVID(e.target.value)}
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Text>PID (产品 ID):</Text>
            <Input
              placeholder="例如: 5591"
              value={newBlockPID}
              onChange={(e) => setNewBlockPID(e.target.value)}
              style={{ marginTop: 4 }}
            />
          </div>
        </Space>
      </Modal>
    </div>
  );
};

export default USB;

import React from 'react';
import { Table, Button, Space, Popconfirm, Tag, Typography } from 'antd';
import {
  StopOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ProcessTableProps, ProcessInfo } from '../types';

const { Text } = Typography;

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

const columns: ColumnsType<ProcessInfo> = [
  {
    title: 'PID',
    dataIndex: 'pid',
    key: 'pid',
    width: 80,
    sorter: (a, b) => a.pid - b.pid,
  },
  {
    title: '进程名称',
    dataIndex: 'name',
    key: 'name',
    width: 180,
    render: (name: string, record: ProcessInfo) => (
      <Space>
        {record.is_blacklisted && (
          <WarningOutlined style={{ color: '#ff4d4f' }} />
        )}
        <Text
          style={{
            color: record.is_blacklisted ? '#ff4d4f' : undefined,
            fontWeight: record.is_blacklisted ? 600 : undefined,
          }}
        >
          {name}
        </Text>
        {record.is_whitelisted && (
          <Tag color="green" style={{ fontSize: 10 }}>白名单</Tag>
        )}
      </Space>
    ),
  },
  {
    title: 'CPU %',
    dataIndex: 'cpu_percent',
    key: 'cpu_percent',
    width: 100,
    sorter: (a, b) => a.cpu_percent - b.cpu_percent,
    render: (val: number) => {
      const color = val > 50 ? '#ff4d4f' : val > 20 ? '#fa8c16' : '#52c41a';
      return <Text style={{ color }}>{val.toFixed(1)}%</Text>;
    },
  },
  {
    title: '内存 %',
    dataIndex: 'memory_percent',
    key: 'memory_percent',
    width: 100,
    sorter: (a, b) => a.memory_percent - b.memory_percent,
    render: (val: number) => {
      const color = val > 30 ? '#ff4d4f' : val > 10 ? '#fa8c16' : '#52c41a';
      return <Text style={{ color }}>{val.toFixed(1)}%</Text>;
    },
  },
  {
    title: '内存占用',
    dataIndex: 'memory_rss',
    key: 'memory_rss',
    width: 120,
    render: (val: number) => formatBytes(val),
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100,
    render: (status: string) => (
      <Tag color={status === 'running' ? 'green' : 'default'}>{status}</Tag>
    ),
  },
  {
    title: '路径',
    dataIndex: 'exe_path',
    key: 'exe_path',
    ellipsis: true,
    width: 200,
    render: (path: string) => (
      <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: path }}>
        {path || '-'}
      </Text>
    ),
  },
];

const ProcessTable: React.FC<ProcessTableProps> = ({
  processes,
  loading,
  onKill,
  onRefresh,
}) => {
  const actionColumn: ColumnsType<ProcessInfo>[0] = {
    title: '操作',
    key: 'actions',
    width: 100,
    fixed: 'right',
    render: (_: unknown, record: ProcessInfo) => (
      <Popconfirm
        title="终止进程"
        description={`确定要终止 ${record.name} (PID: ${record.pid}) 吗？`}
        onConfirm={() => onKill(record.pid)}
        okText="确定"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <Button
          type="link"
          danger
          size="small"
          icon={<StopOutlined />}
        >
          终止
        </Button>
      </Popconfirm>
    ),
  };

  return (
    <Table<ProcessInfo>
      dataSource={processes}
      columns={[...columns, actionColumn]}
      rowKey="pid"
      loading={loading}
      size="small"
      scroll={{ x: 1000 }}
      pagination={{
        pageSize: 50,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 个进程`,
      }}
      title={() => (
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Text strong>进程列表</Text>
          <Button
            icon={<ReloadOutlined />}
            size="small"
            onClick={onRefresh}
            loading={loading}
          >
            刷新
          </Button>
        </Space>
      )}
    />
  );
};

export default ProcessTable;

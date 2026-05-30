import React, { useEffect, useMemo, useState } from 'react';
import {
  Card,
  Table,
  Typography,
  Space,
  Select,
  Tag,
  Row,
  Col,
  Statistic,
  Button,
  Tooltip,
  Empty,
  Descriptions,
  Modal,
} from 'antd';
import {
  AlertOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  EyeOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts';
import { useStore } from '../store';
import type { Alert, AlertSeverity, AlertType, SmartControlInfo } from '../types';
import AlertBadge from '../components/AlertBadge';

const { Title, Text } = Typography;

const severityColors: Record<string, string> = {
  critical: '#ff4d4f',
  warn: '#fa8c16',
  info: '#1677ff',
};

const severityLabels: Record<AlertSeverity, string> = {
  info: '信息',
  warn: '警告',
  critical: '严重',
};

const typeLabels: Record<string, string> = {
  process: '进程',
  usb: 'USB',
  network: '网络',
  system: '系统',
  sandbox: '沙箱',
};

const PIE_COLORS = ['#ff4d4f', '#fa8c16', '#1677ff'];

const Alerts: React.FC = () => {
  const {
    alerts,
    loading,
    fetchAlerts,
    smartControl,
    fetchStatus,
  } = useStore();
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | 'all'>('all');
  const [typeFilter, setTypeFilter] = useState<AlertType | 'all'>('all');
  const [detailAlert, setDetailAlert] = useState<Alert | null>(null);

  useEffect(() => {
    fetchAlerts({ severity: severityFilter === 'all' ? undefined : severityFilter });
    fetchStatus();
  }, [severityFilter]);

  const handleRefresh = () => {
    fetchAlerts({ severity: severityFilter === 'all' ? undefined : severityFilter });
    fetchStatus();
  };

  // -- Derived data for charts --
  const severityDist = useMemo(() => {
    const counts = { critical: 0, warn: 0, info: 0 };
    alerts.forEach((a) => {
      if (a.severity in counts) counts[a.severity as keyof typeof counts]++;
    });
    return [
      { name: '严重', value: counts.critical, color: '#ff4d4f' },
      { name: '警告', value: counts.warn, color: '#fa8c16' },
      { name: '信息', value: counts.info, color: '#1677ff' },
    ];
  }, [alerts]);

  const typeDist = useMemo(() => {
    const counts: Record<string, number> = {};
    alerts.forEach((a) => {
      const key = a.type || 'system';
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([key, value]) => ({ name: typeLabels[key] || key, value }))
      .sort((a, b) => b.value - a.value);
  }, [alerts]);

  const trendData = useMemo(() => {
    const hourly: Record<string, { hour: string; critical: number; warn: number; info: number }> = {};
    const now = Date.now();
    for (let i = 23; i >= 0; i--) {
      const h = new Date(now - i * 3600_000);
      const key = `${h.getHours().toString().padStart(2, '0')}:00`;
      hourly[key] = { hour: key, critical: 0, warn: 0, info: 0 };
    }
    alerts.forEach((a) => {
      const ts = a.timestamp ? new Date(a.timestamp).getTime() : 0;
      const hoursAgo = Math.floor((now - ts) / 3600_000);
      if (hoursAgo >= 0 && hoursAgo < 24) {
        const h = new Date(now - hoursAgo * 3600_000);
        const key = `${h.getHours().toString().padStart(2, '0')}:00`;
        if (hourly[key]) {
          if (a.severity === 'critical') hourly[key].critical++;
          else if (a.severity === 'warn') hourly[key].warn++;
          else hourly[key].info++;
        }
      }
    });
    return Object.values(hourly);
  }, [alerts]);

  const unacknowledgedCount = useMemo(
    () => alerts.filter((a) => !a.acknowledged).length,
    [alerts]
  );

  const criticalCount = useMemo(
    () => alerts.filter((a) => a.severity === 'critical').length,
    [alerts]
  );

  // -- Table columns --
  const columns: ColumnsType<Alert> = [
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (sev: AlertSeverity) => <AlertBadge severity={sev} />,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 80,
      render: (type: string) => <Tag>{typeLabels[type] || type}</Tag>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 220,
      render: (title: string, record: Alert) => (
        <Text
          style={{
            color:
              record.severity === 'critical'
                ? '#ff4d4f'
                : record.severity === 'warn'
                  ? '#fa8c16'
                  : undefined,
          }}
        >
          {title}
        </Text>
      ),
    },
    {
      title: '详情',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (msg: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {msg}
        </Text>
      ),
    },
    {
      title: '响应动作',
      dataIndex: 'details',
      key: 'action',
      width: 120,
      render: (details: Record<string, unknown>) => {
        const action = details?.action_taken as string | undefined;
        if (!action || action === 'log_only') return <Text type="secondary">-</Text>;
        return <Tag color="purple">{action}</Tag>;
      },
    },
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 170,
      sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
      defaultSortOrder: 'descend',
      render: (ts: string | number) => new Date(ts).toLocaleString('zh-CN'),
    },
    {
      title: '状态',
      dataIndex: 'acknowledged',
      key: 'acknowledged',
      width: 90,
      render: (ack: boolean) => (
        <Tag color={ack ? 'default' : 'red'}>{ack ? '已确认' : '未确认'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 60,
      render: (_: unknown, record: Alert) => (
        <Tooltip title="查看详情">
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setDetailAlert(record)}
          />
        </Tooltip>
      ),
    },
  ];

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <AlertOutlined /> 告警联动仪表盘
      </Title>

      {/* Health Score + Statistic Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="系统健康分"
              value={smartControl?.health_score ?? '-'}
              suffix={smartControl?.health_score !== undefined ? '分' : ''}
              valueStyle={{
                color:
                  (smartControl?.health_score ?? 100) >= 80
                    ? '#52c41a'
                    : (smartControl?.health_score ?? 100) >= 50
                      ? '#fa8c16'
                      : '#ff4d4f',
              }}
              prefix={<HeartOutlined />}
            />
            {smartControl?.tuner_multiplier !== undefined && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                监控倍率: x{smartControl.tuner_multiplier}
              </Text>
            )}
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="未确认告警"
              value={unacknowledgedCount}
              valueStyle={{ color: unacknowledgedCount > 0 ? '#fa8c16' : '#52c41a' }}
              prefix={<WarningOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="严重告警"
              value={criticalCount}
              valueStyle={{ color: criticalCount > 0 ? '#ff4d4f' : '#52c41a' }}
              prefix={<AlertOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic
              title="告警总数"
              value={alerts.length}
              prefix={<InfoCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Charts Row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={8}>
          <Card title="严重程度分布" size="small">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={severityDist.filter((d) => d.value > 0)}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, percent }) =>
                    `${name} ${(percent * 100).toFixed(0)}%`
                  }
                >
                  {severityDist.map((entry, i) => (
                    <Cell key={i} fill={entry.color || PIE_COLORS[i]} />
                  ))}
                </Pie>
                <ReTooltip />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="告警类型分布" size="small">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={typeDist} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis type="category" dataKey="name" width={50} />
                <ReTooltip />
                <Bar dataKey="value" fill="#1677ff" barSize={20} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="24 小时趋势" size="small">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} interval={3} />
                <YAxis allowDecimals={false} />
                <ReTooltip />
                <Line
                  type="monotone"
                  dataKey="critical"
                  stroke="#ff4d4f"
                  name="严重"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="warn"
                  stroke="#fa8c16"
                  name="警告"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="info"
                  stroke="#1677ff"
                  name="信息"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      {/* Alert Table */}
      <Card
        title={
          <Space>
            <span>告警记录</span>
            <Tag>{alerts.length}</Tag>
          </Space>
        }
        size="small"
        extra={
          <Button icon={<ReloadOutlined />} size="small" onClick={handleRefresh}>
            刷新
          </Button>
        }
      >
        <Space style={{ marginBottom: 16 }}>
          <span style={{ color: 'rgba(255,255,255,0.65)' }}>严重程度: </span>
          <Select
            value={severityFilter}
            onChange={setSeverityFilter}
            style={{ width: 120 }}
            options={[
              { value: 'all', label: '全部' },
              { value: 'info', label: '信息' },
              { value: 'warn', label: '警告' },
              { value: 'critical', label: '严重' },
            ]}
          />
          <span style={{ color: 'rgba(255,255,255,0.65)' }}>类型: </span>
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            style={{ width: 100 }}
            options={[
              { value: 'all', label: '全部' },
              { value: 'process', label: '进程' },
              { value: 'usb', label: 'USB' },
              { value: 'system', label: '系统' },
              { value: 'sandbox', label: '沙箱' },
            ]}
          />
        </Space>

        <Table<Alert>
          dataSource={alerts.filter(
            (a) => typeFilter === 'all' || a.type === typeFilter
          )}
          columns={columns}
          rowKey="id"
          loading={loading.alerts}
          size="small"
          scroll={{ x: 1000 }}
          pagination={{
            pageSize: 15,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条告警`,
          }}
          locale={{
            emptyText: (
              <Empty description="暂无告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ),
          }}
        />
      </Card>

      {/* Detail Modal */}
      <Modal
        title="告警详情"
        open={!!detailAlert}
        onCancel={() => setDetailAlert(null)}
        footer={null}
        width={600}
      >
        {detailAlert && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="ID" span={2}>
              <Text copyable>{detailAlert.id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="严重程度">
              <Tag color={severityColors[detailAlert.severity]}>
                {severityLabels[detailAlert.severity] || detailAlert.severity}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="类型">
              <Tag>{typeLabels[detailAlert.type] || detailAlert.type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="标题" span={2}>
              {detailAlert.title}
            </Descriptions.Item>
            <Descriptions.Item label="消息" span={2}>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                  fontSize: 12,
                }}
              >
                {detailAlert.message}
              </pre>
            </Descriptions.Item>
            <Descriptions.Item label="时间" span={2}>
              {new Date(detailAlert.timestamp).toLocaleString('zh-CN')}
            </Descriptions.Item>
            <Descriptions.Item label="已确认">
              <Tag color={detailAlert.acknowledged ? 'green' : 'red'}>
                {detailAlert.acknowledged ? '是' : '否'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="响应动作">
              {(detailAlert.details?.action_taken as string) ? (
                <Tag color="purple">
                  {detailAlert.details?.action_taken as string}
                </Tag>
              ) : (
                <Text type="secondary">-</Text>
              )}
            </Descriptions.Item>
            {detailAlert.details &&
              Object.entries(detailAlert.details)
                .filter(([k]) => k !== 'action_taken')
                .map(([key, val]) => (
                  <Descriptions.Item label={key} key={key} span={2}>
                    {typeof val === 'object'
                      ? JSON.stringify(val, null, 2)
                      : String(val)}
                  </Descriptions.Item>
                ))}
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default Alerts;

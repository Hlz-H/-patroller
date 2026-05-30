import React, { useEffect } from 'react';
import { Row, Col, Card, Typography, List, Tag, Spin, Empty, Progress } from 'antd';
import {
  DashboardOutlined,
  ApiOutlined,
  HddOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import {
  PieChart, Pie, Cell,
  BarChart, Bar,
  LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useStore } from '../store';
import StatusCard from '../components/StatusCard';

const { Title, Text } = Typography;

const COLORS = ['#1677ff', '#e8e8e8'];

const severityTagColors: Record<string, string> = {
  info: 'blue',
  warn: 'orange',
  critical: 'red',
};

const Dashboard: React.FC = () => {
  const {
    systemMetrics, status, alerts, loading,
    processTotal, alertTotal,
    metricsHistory, fetchMetricsHistory,
  } = useStore();

  useEffect(() => {
    fetchMetricsHistory(60);
    const timer = setInterval(() => fetchMetricsHistory(60), 60000);
    return () => clearInterval(timer);
  }, []);

  const cpuData = systemMetrics
    ? [
        { name: '已使用', value: systemMetrics.cpu_percent },
        { name: '空闲', value: 100 - systemMetrics.cpu_percent },
      ]
    : [];

  const memPercent = systemMetrics?.memory_percent ?? 0;
  const diskPercent = systemMetrics?.disk_percent ?? 0;

  const recentAlerts = alerts.slice(0, 10);

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <DashboardOutlined /> 系统仪表盘
      </Title>

      {/* Stat Cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard
            label="CPU 使用率"
            value={systemMetrics?.cpu_percent ?? 0}
            unit="%"
            color="#1677ff"
            icon={<CloudServerOutlined />}
            loading={loading.status}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard
            label="内存使用率"
            value={systemMetrics?.memory_percent ?? 0}
            unit="%"
            color="#52c41a"
            icon={<DashboardOutlined />}
            loading={loading.status}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard
            label="磁盘使用率"
            value={systemMetrics?.disk_percent ?? 0}
            unit="%"
            color="#fa8c16"
            icon={<HddOutlined />}
            loading={loading.status}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatusCard
            label="网络接收"
            value={
              systemMetrics
                ? `${((systemMetrics.network_bytes_recv || 0) / 1024).toFixed(1)} KB/s`
                : '0'
            }
            unit=""
            color="#722ed1"
            icon={<ApiOutlined />}
            loading={loading.status}
          />
        </Col>
      </Row>

      {/* Charts */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={8}>
          <Card title="CPU 使用率" size="small">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={cpuData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {cpuData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={index === 0 ? '#1677ff' : '#e8e8e8'}
                    />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => `${value.toFixed(1)}%`} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ textAlign: 'center', marginTop: -20 }}>
              <Text style={{ fontSize: 22, fontWeight: 700 }}>
                {systemMetrics?.cpu_percent?.toFixed(1) ?? 0}%
              </Text>
              <br />
              <Text type="secondary">{systemMetrics?.cpu_count ?? 0} 核</Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="内存使用" size="small">
            <div style={{ padding: '20px 0' }}>
              <Progress
                type="dashboard"
                percent={memPercent}
                strokeColor={{
                  '0%': '#52c41a',
                  '70%': '#fa8c16',
                  '90%': '#ff4d4f',
                }}
                format={(p) => `${p?.toFixed(1)}%`}
              />
              <div style={{ textAlign: 'center' }}>
                <Text type="secondary">
                  {systemMetrics
                    ? `${((systemMetrics.memory_used || 0) / (1024 * 1024 * 1024)).toFixed(1)} / ${((systemMetrics.memory_total || 1) / (1024 * 1024 * 1024)).toFixed(1)} GB`
                    : '-'}
                </Text>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="磁盘使用" size="small">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={[{ name: '磁盘', used: diskPercent, free: 100 - diskPercent }]}
                layout="vertical"
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" domain={[0, 100]} unit="%" />
                <YAxis type="category" dataKey="name" hide />
                <Tooltip formatter={(value: number) => `${value.toFixed(1)}%`} />
                <Bar dataKey="used" fill="#fa8c16" stackId="a" barSize={30} />
                <Bar dataKey="free" fill="#e8e8e8" stackId="a" barSize={30} />
              </BarChart>
            </ResponsiveContainer>
            <div style={{ textAlign: 'center' }}>
              <Text type="secondary">
                {systemMetrics
                  ? `${((systemMetrics.disk_used || 0) / (1024 * 1024 * 1024)).toFixed(1)} / ${((systemMetrics.disk_total || 1) / (1024 * 1024 * 1024)).toFixed(1)} GB`
                  : '-'}
              </Text>
            </div>
          </Card>
        </Col>
      </Row>

      {/* Trend Charts — 60-minute history */}
      {metricsHistory.length > 1 && (
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} lg={8}>
            <Card title="CPU 趋势（60 分）" size="small">
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={metricsHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(ts: number) => {
                      const d = new Date(ts);
                      return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
                    }}
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis domain={[0, 100]} hide />
                  <Tooltip
                    labelFormatter={(ts: number) => new Date(ts).toLocaleString('zh-CN')}
                    formatter={(value: unknown) => [`${Number(value).toFixed(1)}%`, 'CPU']}
                  />
                  <Line type="monotone" dataKey="cpuUsage" stroke="#1677ff" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="内存趋势（60 分）" size="small">
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={metricsHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(ts: number) => {
                      const d = new Date(ts);
                      return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
                    }}
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis domain={[0, 100]} hide />
                  <Tooltip
                    labelFormatter={(ts: number) => new Date(ts).toLocaleString('zh-CN')}
                    formatter={(value: unknown) => [`${Number(value).toFixed(1)}%`, '内存']}
                  />
                  <Line type="monotone" dataKey="memoryUsage" stroke="#52c41a" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          </Col>
          <Col xs={24} lg={8}>
            <Card title="磁盘趋势（60 分）" size="small">
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={metricsHistory}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(ts: number) => {
                      const d = new Date(ts);
                      return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
                    }}
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis domain={[0, 100]} hide />
                  <Tooltip
                    labelFormatter={(ts: number) => new Date(ts).toLocaleString('zh-CN')}
                    formatter={(value: unknown) => [`${Number(value).toFixed(1)}%`, '磁盘']}
                  />
                  <Line type="monotone" dataKey="diskUsage" stroke="#fa8c16" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          </Col>
        </Row>
      )}

      {/* Process + Alerts summary + Recent Alerts */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="运行概况" size="small">
            {loading.status ? (
              <Spin />
            ) : (
              <Row gutter={[16, 16]}>
                <Col span={12}>
                  <StatusCard
                    label="进程总数"
                    value={processTotal}
                    color="#1677ff"
                    loading={false}
                  />
                </Col>
                <Col span={12}>
                  <StatusCard
                    label="告警总数"
                    value={alertTotal}
                    color="#ff4d4f"
                    loading={false}
                  />
                </Col>
                <Col span={12}>
                  <StatusCard
                    label="运行时间"
                    value={status ? `${Math.floor(status.uptime / 3600)}h` : '-'}
                    color="#52c41a"
                    loading={false}
                  />
                </Col>
                <Col span={12}>
                  <StatusCard
                    label="监控状态"
                    value={status?.monitor_enabled ? '运行' : '停止'}
                    color={status?.monitor_enabled ? '#52c41a' : '#ff4d4f'}
                    loading={false}
                  />
                </Col>
              </Row>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="最近告警" size="small">
            {recentAlerts.length === 0 ? (
              <Empty description="暂无告警" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                size="small"
                dataSource={recentAlerts}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={
                        <Tag color={severityTagColors[item.severity]}>
                          {item.severity === 'critical'
                            ? '严重'
                            : item.severity === 'warn'
                              ? '警告'
                              : '信息'}
                        </Tag>
                      }
                      title={
                        <Text
                          style={{
                            color: item.severity === 'critical' ? '#ff4d4f' : undefined,
                          }}
                        >
                          {item.title}
                        </Text>
                      }
                      description={
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {item.message} · {new Date(item.timestamp).toLocaleString('zh-CN')}
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Dashboard;

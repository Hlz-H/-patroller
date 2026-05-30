import React, { useEffect, useState } from 'react';
import {
  Card,
  Typography,
  Tag,
  Row,
  Col,
  Input,
  Button,
  Spin,
  Alert,
  Descriptions,
  Divider,
  Space,
  Tooltip,
} from 'antd';
import {
  SafetyOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  FileTextOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { useStore } from '../store';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const Sandbox: React.FC = () => {
  const {
    sandboxStatus,
    sandboxRunning,
    sandboxLastResult,
    loading,
    fetchSandboxStatus,
    runSandbox,
  } = useStore();

  const [filePath, setFilePath] = useState('');

  useEffect(() => {
    fetchSandboxStatus();
  }, []);

  const handleRun = () => {
    if (!filePath.trim()) return;
    runSandbox(filePath.trim());
  };

  const renderStatus = () => {
    if (loading.sandbox) return <Spin />;
    if (!sandboxStatus) return <Text type="secondary">无法获取沙箱状态</Text>;

    const enabled = sandboxStatus.enabled && sandboxStatus.available;
    return (
      <Descriptions column={2} size="small" bordered>
        <Descriptions.Item label="状态">
          <Tag color={enabled ? 'green' : 'red'} icon={enabled ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
            {enabled ? '可用' : '不可用'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="超时时间">
          {sandboxStatus.timeout_seconds ?? 120} 秒
        </Descriptions.Item>
        <Descriptions.Item label="enabled" span={2}>
          <Text code>{String(sandboxStatus.enabled)}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="available" span={2}>
          <Text code>{String(sandboxStatus.available)}</Text>
        </Descriptions.Item>
        {sandboxStatus.reason && (
          <Descriptions.Item label="原因" span={2}>
            <Text type="warning">{sandboxStatus.reason}</Text>
          </Descriptions.Item>
        )}
      </Descriptions>
    );
  };

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <SafetyOutlined /> 沙箱管理
      </Title>

      {/* Status Card */}
      <Card title="沙箱状态" size="small" style={{ marginBottom: 24 }}>
        {renderStatus()}
      </Card>

      {/* Run Card */}
      <Card
        title={
          <Space>
            <PlayCircleOutlined />
            运行文件
          </Space>
        }
        size="small"
        style={{ marginBottom: 24 }}
      >
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Input
              placeholder="输入文件路径，如 C:\Users\test\sample.exe"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              onPressEnter={handleRun}
              disabled={sandboxRunning}
              prefix={<FileTextOutlined />}
              allowClear
            />
          </Col>
          <Col>
            <Tooltip title="在 Windows Sandbox 中运行并分析">
              <Button
                type="primary"
                icon={sandboxRunning ? <LoadingOutlined /> : <PlayCircleOutlined />}
                onClick={handleRun}
                loading={sandboxRunning}
                disabled={!filePath.trim() || !sandboxStatus?.enabled}
              >
                {sandboxRunning ? '运行中...' : '运行并分析'}
              </Button>
            </Tooltip>
          </Col>
        </Row>
      </Card>

      {/* Result Card */}
      {sandboxLastResult && (
        <Card
          title={
            <Space>
              <RobotOutlined />
              分析结果
            </Space>
          }
          size="small"
        >
          {sandboxLastResult.report ? (
            <>
              <Text strong>行为报告：</Text>
              <div style={{ marginTop: 8, marginBottom: 16 }}>
                <pre
                  style={{
                    background: '#1a1a1a',
                    padding: 12,
                    borderRadius: 6,
                    fontSize: 12,
                    maxHeight: 300,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                  }}
                >
                  {typeof sandboxLastResult.report === 'object'
                    ? JSON.stringify(sandboxLastResult.report, null, 2)
                    : String(sandboxLastResult.report)}
                </pre>
              </div>
            </>
          ) : (
            <Text type="secondary">沙箱未生成行为报告</Text>
          )}

          {sandboxLastResult.analysis ? (
            <>
              <Divider />
              <Text strong>AI 分析：</Text>
              <div style={{ marginTop: 8 }}>
                {typeof sandboxLastResult.analysis === 'object' ? (
                  <Descriptions column={1} size="small" bordered>
                    {Object.entries(
                      sandboxLastResult.analysis as Record<string, unknown>
                    ).map(([key, val]) => (
                      <Descriptions.Item label={key} key={key}>
                        {typeof val === 'object'
                          ? JSON.stringify(val, null, 2)
                          : String(val)}
                      </Descriptions.Item>
                    ))}
                  </Descriptions>
                ) : (
                  <Paragraph
                    style={{
                      background: '#1a1a1a',
                      padding: 12,
                      borderRadius: 6,
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {String(sandboxLastResult.analysis)}
                  </Paragraph>
                )}
              </div>
            </>
          ) : null}

          {!sandboxLastResult.report && !sandboxLastResult.analysis && (
            <Alert
              message="无结果"
              description="沙箱运行未返回任何数据，请检查 Agent 日志"
              type="warning"
              showIcon
            />
          )}
        </Card>
      )}
    </div>
  );
};

export default Sandbox;

import React from 'react';
import { Tag } from 'antd';
import {
  InfoCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { AlertSeverity } from '../types';

const severityConfig: Record<AlertSeverity, { color: string; icon: React.ReactNode; label: string }> = {
  info: { color: '#1677ff', icon: <InfoCircleOutlined />, label: '信息' },
  warn: { color: '#fa8c16', icon: <WarningOutlined />, label: '警告' },
  critical: { color: '#ff4d4f', icon: <CloseCircleOutlined />, label: '严重' },
};

interface AlertBadgeProps {
  severity: AlertSeverity;
  count?: number;
}

const AlertBadge: React.FC<AlertBadgeProps> = ({ severity, count }) => {
  const config = severityConfig[severity];
  return (
    <Tag
      color={config.color}
      icon={config.icon}
      style={{ margin: 0 }}
    >
      {config.label}
      {count !== undefined && count > 0 && ` (${count})`}
    </Tag>
  );
};

export default AlertBadge;

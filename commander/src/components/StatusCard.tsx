import React from 'react';
import { Card, Statistic, Skeleton } from 'antd';
import type { StatusCardProps } from '../types';

const StatusCard: React.FC<StatusCardProps> = ({
  label,
  value,
  unit = '',
  color = '#1677ff',
  icon,
  loading = false,
}) => {
  return (
    <Card
      hoverable
      style={{
        borderLeft: `4px solid ${color}`,
        height: '100%',
      }}
      styles={{ body: { padding: '20px 24px' } }}
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 1 }} />
      ) : (
        <Statistic
          title={
            <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.65)' }}>
              {icon && <span style={{ marginRight: 6 }}>{icon}</span>}
              {label}
            </span>
          }
          value={typeof value === 'number' ? value : value}
          suffix={
            unit ? (
              <span style={{ fontSize: 14, color: 'rgba(255,255,255,0.45)' }}>
                {unit}
              </span>
            ) : undefined
          }
          valueStyle={{
            color: '#fff',
            fontSize: 28,
            fontWeight: 600,
          }}
        />
      )}
    </Card>
  );
};

export default StatusCard;

import React, { useEffect, useState } from 'react';
import { Card, Input, Space, Typography, message, Select } from 'antd';
import { AppstoreOutlined, SearchOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import ProcessTable from '../components/ProcessTable';

const { Title } = Typography;
const { Search } = Input;

const Processes: React.FC = () => {
  const { processes, loading, fetchProcesses, killProcess } = useStore();
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<string>('cpu_percent');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    fetchProcesses({ search: search || undefined, sort_by: sortBy, sort_order: sortOrder });
  }, [search, sortBy, sortOrder]);

  const handleKill = async (pid: number) => {
    const success = await killProcess(pid);
    if (success) {
      message.success(`已发送终止进程 ${pid} 的指令`);
      fetchProcesses({ search: search || undefined, sort_by: sortBy, sort_order: sortOrder });
    } else {
      message.error(`终止进程 ${pid} 失败`);
    }
  };

  const handleRefresh = () => {
    fetchProcesses({ search: search || undefined, sort_by: sortBy, sort_order: sortOrder });
  };

  const handleSearch = (value: string) => {
    setSearch(value);
  };

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        <AppstoreOutlined /> 进程管理
      </Title>

      <Card>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Search
            placeholder="搜索进程名称..."
            allowClear
            onSearch={handleSearch}
            onChange={(e) => !e.target.value && setSearch('')}
            style={{ width: 300 }}
            prefix={<SearchOutlined />}
          />
          <Space>
            <span style={{ color: 'rgba(255,255,255,0.65)' }}>排序: </span>
            <Select
              value={sortBy}
              onChange={setSortBy}
              style={{ width: 120 }}
              options={[
                { value: 'cpu_percent', label: 'CPU' },
                { value: 'memory_percent', label: '内存' },
                { value: 'pid', label: 'PID' },
                { value: 'name', label: '名称' },
              ]}
            />
            <Select
              value={sortOrder}
              onChange={setSortOrder}
              style={{ width: 80 }}
              options={[
                { value: 'desc', label: '降序' },
                { value: 'asc', label: '升序' },
              ]}
            />
          </Space>
        </Space>

        <ProcessTable
          processes={processes}
          loading={loading.processes}
          onKill={handleKill}
          onRefresh={handleRefresh}
        />
      </Card>
    </div>
  );
};

export default Processes;

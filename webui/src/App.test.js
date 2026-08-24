import { render, screen } from '@testing-library/react';
import App from './App';

// 冒烟测试：未登录时应用应渲染出登录页（而非崩溃）。
// 注意：未登录状态下 useWebSocket 不会建立连接（"登录后才连接"），
// 因此 jsdom 中无需 WebSocket 实现也能渲染。
test('未登录时渲染登录页', async () => {
  render(<App />);
  // PrivateRoute 会把未认证访问重定向到 /login，登录页标题为"用户登录"
  expect(await screen.findByText('用户登录')).toBeInTheDocument();
});

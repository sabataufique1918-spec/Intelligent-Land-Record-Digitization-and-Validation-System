import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="empty">
      <h1>Page not found</h1>
      <p>
        <Link to="/" className="link">Back to dashboard</Link>
      </p>
    </div>
  )
}

const jwt = require('jsonwebtoken');
const { getUserById } = require('../db/users');

const authMiddleware = async (req, res, next) => {
  try {
    const token = req.header('Authorization')?.replace('Bearer ', '');
    
    if (!token) {
      return res.status(401).json({ error: 'Access denied. No token provided.' });
    }

    const decoded = jwt.verify(token, process.env.JWT_SECRET || 'your-secret-key');
    const user = await getUserById(decoded.userId);
    
    if (!user) {
      return res.status(401).json({ error: 'Invalid token.' });
    }

    if (!user.isActive) {
      return res.status(401).json({ error: 'Account is inactive.' });
    }

    // Match previous shape used by routes
    req.user = {
      _id: user.userId,
      username: user.username,
      email: user.email,
      role: user.role,
      isActive: user.isActive,
    };
    next();
  } catch (error) {
    res.status(401).json({ error: 'Invalid token.' });
  }
};

// No admin middleware: app supports only regular user authentication
module.exports = { authMiddleware };
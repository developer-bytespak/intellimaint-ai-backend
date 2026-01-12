import { Injectable } from '@nestjs/common';
import { PrismaService } from 'prisma/prisma.service';
import { nestError, nestResponse } from 'src/common/helpers/responseHelpers';

@Injectable()
export class AdminService {
  constructor(private prisma: PrismaService) { }
  async getAllUsers(res: Response) {
    const users = await this.prisma.user.findMany({
      include: {
        repositories: true,
        chatSessions: true,
        subscriptions: true,
      },
    });
    if (!users) {
      return nestError(404, 'No users found')(res as any);
    }

    const formattedUsers = users.map(user => ({
      id: user.id,
      name: `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim(),
      email: user.email,
      role: user.role,
      profileImage: user.profileImageUrl ?? `https://api.dicebear.com/7.x/avataaars/svg?seed=${user.firstName ?? 'User'}`,
      status: user.status.toLowerCase(),
      createdAt: user.createdAt,
      uploads: user.repositories?.length ?? 0,
      sessions: user.chatSessions?.length ?? 0,
      subscriptionPlan: user.subscriptions?.[0]?.planName ?? 'free',
    }));
    return nestResponse(200, "Users get Successfully!", formattedUsers)(res as any);
  }

  async getAllUploads(res: Response) {
    const uploads = await this.prisma.repository.findMany({
      include: {
        user: true,
      },
    });
    if (!uploads) {
      return nestError(404, 'No uploads found')(res as any);
    }

    const formattedUploads = uploads.map((upload, idx) => ({
      id: (idx + 1).toString(),
      userId: upload.userId,
      userName: `${upload.user?.firstName ?? ''} ${upload.user?.lastName ?? ''}`.trim(),
      fileName: upload.fileName,
      fileType: upload.fileName?.split('.').pop()?.toUpperCase() ?? '',
      fileSize: upload.fileSize,
      status: upload.status,
      uploadedAt: upload.uploadedAt,
      completedAt: upload.createdAt, // If you have a completedAt field, use it; else, fallback to createdAt
    }));

    return nestResponse(200, "Uploads get Successfully!", formattedUploads)(res as any);
  }

  async getAllSubscriptions(res: Response) {
    const subscriptions = await this.prisma.subscription.findMany({
      include: {
        user: true,
      },
    });
    if (!subscriptions) {
      return nestError(404, 'No subscriptions found')(res as any);
    }
  }

  // filepath: 
  async getUserChatStats(res: Response) {
    // Pricing for each model
    const pricing = {
      'gpt-4o': { prompt: 0.000005, completion: 0.000015 },
      'gpt-4o-mini': { prompt: 0.0000015, completion: 0.0000075 },
    };

    const users = await this.prisma.user.findMany({
      include: {
        chatSessions: {
          include: {
            messages: true,
          },
        },
      },
    });

    if (!users) {
      return nestError(404, 'No users found')(res as any);
    }

    const formatted = users.map(user => {
      let totalMessages = 0;
      let userToken = 0;
      let systemToken = 0;
      let totalToken = 0;
      let totalPrice = 0;

      user.chatSessions.forEach(session => {
        totalMessages += session.messages.length;

        session.messages
          .filter(msg => msg.role === 'assistant')
          .forEach(msg => {
            const model = msg.model ?? 'gpt-4o-mini'; // Default to mini if not set
            const modelPricing = pricing[model] || pricing['gpt-4o-mini'];

            userToken += msg.promptTokens ?? 0;
            systemToken += msg.completionTokens ?? 0;
            totalToken += (msg.promptTokens ?? 0) + (msg.completionTokens ?? 0);

            totalPrice += ((msg.promptTokens ?? 0) * modelPricing.prompt) +
              ((msg.completionTokens ?? 0) * modelPricing.completion);
          });
      });

      return {
        id: user.id,
        email: user.email,
        totalSessions: user.chatSessions.length,
        totalMessages,
        userToken,
        systemToken,
        totalToken,
        totalPrice: +totalPrice.toFixed(4),
      };
    });

    return nestResponse(200, "User chat stats fetched successfully!", formatted)(res as any);
  }

  async getDashboardStats(res: Response, year?: number, month?: number) {
    // Helper to get start/end dates
    function getDateRange(year?: number, month?: number) {
      if (year && month) {
        // Specific month in year
        const start = new Date(year, month - 1, 1);
        const end = new Date(year, month, 1);
        return { start, end };
      } else if (year) {
        // Whole year
        const start = new Date(year, 0, 1);
        const end = new Date(year + 1, 0, 1);
        return { start, end };
      }
      // All time
      return { start: undefined, end: undefined };
    }

    // Get date range for filtering
    const { start, end } = getDateRange(year, month);

    // Time series aggregation helpers
    async function getMonthlyCounts(model, dateField = 'createdAt', filter = {}) {
      const where = { ...filter };
      if (start && end) {
        where[dateField] = { gte: start, lt: end };
      } else if (start) {
        where[dateField] = { gte: start };
      }
      const records = await model.findMany({ where });
      // Group by month
      const counts = {};
      records.forEach(r => {
        const d = new Date(r[dateField]);
        const key = `${d.getFullYear()}-${('0' + (d.getMonth() + 1)).slice(-2)}`;
        counts[key] = (counts[key] || 0) + 1;
      });
      // Convert to array of { date, value }
      return Object.entries(counts).map(([date, value]) => ({ date, value }));
    }

    async function getYearlyCounts(model, dateField = 'createdAt', filter = {}) {
      const where = { ...filter };
      if (start && end) {
        where[dateField] = { gte: start, lt: end };
      } else if (start) {
        where[dateField] = { gte: start };
      }
      const records = await model.findMany({ where });
      // Group by year
      const counts = {};
      records.forEach(r => {
        const d = new Date(r[dateField]);
        const key = `${d.getFullYear()}`;
        counts[key] = (counts[key] || 0) + 1;
      });
      // Convert to array of { date, value }
      return Object.entries(counts).map(([date, value]) => ({ date, value }));
    }

    // Main stats
    const [totalUsers, activeUsers, totalUploads, readyUploads, activeSessions, activeSubscriptions] = await Promise.all([
      this.prisma.user.count(),
      this.prisma.user.count({ where: { status: 'ACTIVE' } }),
      this.prisma.repository.count(),
      this.prisma.repository.count({ where: { status: 'ready' } }),
      this.prisma.chatSession.count({ where: { status: 'active' } }),
      this.prisma.subscription.count({ where: { status: 'active' } }),
    ]);

    // Users by role
    const usersByRole = {
      student: await this.prisma.user.count({ where: { role: 'student' } }),
      military: await this.prisma.user.count({ where: { role: 'military' } }),
      civilian: await this.prisma.user.count({ where: { role: 'civilian' } }),
    };


    // Subscriptions by plan (dummy)
    const subscriptionsByPlan = {
      free: 8,
      basic: 10,
      pro: 15,
      enterprise: 5,
    };


    // Trends (time series)
    let userTrends, uploadTrends, sessionTrends;
    if (year && !month) {
      // Year selected, show months in that year
      userTrends = await getMonthlyCounts(this.prisma.user);
      uploadTrends = await getMonthlyCounts(this.prisma.repository);
      sessionTrends = await getMonthlyCounts(this.prisma.chatSession);
    } else if (!year) {
      // No year, show all years
      userTrends = await getYearlyCounts(this.prisma.user);
      uploadTrends = await getYearlyCounts(this.prisma.repository);
      sessionTrends = await getYearlyCounts(this.prisma.chatSession);
    } else if (year && month) {
      // Specific month, show months (same as above for now)
      userTrends = await getMonthlyCounts(this.prisma.user);
      uploadTrends = await getMonthlyCounts(this.prisma.repository);
      sessionTrends = await getMonthlyCounts(this.prisma.chatSession);
    }

    // Sort trends by date ascending
    if (userTrends) userTrends = userTrends.sort((a, b) => a.date.localeCompare(b.date));
    if (uploadTrends) uploadTrends = uploadTrends.sort((a, b) => a.date.localeCompare(b.date));
    if (sessionTrends) sessionTrends = sessionTrends.sort((a, b) => a.date.localeCompare(b.date));

    const lastMonthUsers = await this.prisma.user.count({
      where: {
        createdAt: {
          gte: new Date(new Date().setMonth(new Date().getMonth() - 1)),
        },
      }
    });

    const stats = {
      analytics: {
        totalUsers,
        lastMonthUsers,
        activeUsers,
        totalUploads,
        ready:readyUploads,
        totalSessions: activeSessions,
        totalSubscriptions: activeSubscriptions,
        usersByRole,
        subscriptionsByPlan,
      },
      userGrowth: userTrends,
      uploadTrends: uploadTrends,
      sessionTrends: sessionTrends,
    };

    return nestResponse(200, "Dashboard stats fetched successfully!", stats)(res as any);
  }


}
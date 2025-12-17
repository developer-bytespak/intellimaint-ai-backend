import { PrismaClient, UserStatus } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  const email = process.argv[2];
  
  if (!email) {
    console.error('Please provide an email address: npm run activate-user -- email@example.com');
    process.exit(1);
  }

  try {
    const user = await prisma.user.update({
      where: { email },
      data: { status: UserStatus.ACTIVE },
    });
    
    console.log(`✅ User ${user.email} activated successfully!`);
  } catch (error) {
    console.error(`❌ Error activating user:`, error.message);
  } finally {
    await prisma.$disconnect();
  }
}

main();

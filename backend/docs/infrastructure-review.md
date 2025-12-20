# Infrastructure Review for Long-Running Agent Jobs

## Current Configuration

The job runner infrastructure is defined in `.github/cloudformation/northstar-agent.yml`:

- **Task Definition**: `NorthStarJobRunnerTaskDefinition`
- **Resources**: 1 vCPU, 2GB memory
- **Scheduling**: EventBridge Scheduler every 60 minutes (configurable)
- **Timeout**: Default ECS task timeout (typically 30 minutes, can be extended)
- **Execution**: One-shot ECS RunTask that processes due jobs and exits

## Assessment for Long-Running Jobs

### Current Setup is Sufficient

The existing infrastructure is **adequate** for long-running jobs because:

1. **Checkpoint/Resume System**: Jobs can checkpoint before timeout and resume on the next run
2. **Job Dependencies**: Jobs can depend on other jobs, allowing complex workflows
3. **State Persistence**: All state stored in DynamoDB (accessible across runs)
4. **Resource Efficiency**: 1 vCPU / 2GB is sufficient for most AI operations

### When to Consider Separate Task Definition

A separate task definition with higher resources may be needed if:

1. **Very Long Single-Step Operations**: Operations that cannot be checkpointed and must run >30 minutes continuously
2. **High Memory Requirements**: Operations requiring >2GB memory (e.g., processing very large datasets)
3. **CPU-Intensive Operations**: Operations requiring sustained high CPU (e.g., complex data processing)

### Recommendations

**For Now**: Use existing infrastructure with checkpoint/resume

- Jobs checkpoint every 10 steps or 5 minutes
- Jobs resume automatically on next job runner cycle
- Works well for most long-running operations

**Future Enhancement** (if needed):

- Add `NorthStarLongRunningTaskDefinition` with:
  - 2 vCPU, 4GB memory
  - Extended timeout (60+ minutes)
  - Separate schedule or on-demand execution
- Use for jobs that explicitly require extended runtime

## Current Constraints and Workarounds

1. **ECS Task Timeout (~30 min)**:

   - Workaround: Checkpoint before timeout, resume on next run
   - Status: ✅ Handled

2. **Memory (2GB)**:

   - Workaround: Process in batches, checkpoint intermediate results
   - Status: ✅ Sufficient for current operations

3. **CPU (1 vCPU)**:

   - Workaround: Sequential processing (can be parallelized in future)
   - Status: ✅ Sufficient for current operations

4. **Job Runner Frequency (60 min)**:
   - Workaround: Jobs can reschedule themselves with shorter intervals if needed
   - Status: ✅ Acceptable for most use cases

## Conclusion

**No infrastructure changes needed at this time.** The checkpoint/resume system allows long-running jobs to work within existing constraints. Monitor usage and add separate task definition only if specific use cases require it.

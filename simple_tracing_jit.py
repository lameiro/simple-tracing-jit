PUSH, ADD, JUMP, GT, HALT, POP = range(6)

one_simple_loop = [
    PUSH, 0,     # 0
    GT, 50000, 9, # 2
    ADD, 1,       # 5
    JUMP, 2,      # 7
    HALT         # 9
]

two_simple_loops = [
    PUSH, 0,     # 0
    GT, 50000, 9, # 2
    ADD, 1,       # 5
    JUMP, 2,      # 7

    GT, 100000, 16, # 9
    ADD, 2,         # 12
    JUMP, 9,        # 14

    HALT         # 16
]

nested_loops = [
    PUSH, 0,     # 0 - outer loop counter
    GT, 30, 19, # 2 - start of outer loop
    PUSH, 0,     # 5 - inner loop counter
    GT, 15, 14,  # 7 - start of inner loop
    ADD, 1,      # 10
    JUMP, 7,     # 12 - end of inner loop
    POP,         # 14
    ADD, 2,      # 15
    JUMP, 2,      # 17 - end of outer loop

    HALT         # 19
]

#code = one_simple_loop
#code = two_simple_loops
#code = nested_loops

class Interpreter(object):
    def __init__(self, pc, stack, code):
        self.pc = pc
        self.stack = stack
        self.code = code

    def run_PUSH(self):
        #print "Running PUSH"
        self.stack.append(code[self.pc+1])
        self.pc += 2

    def run_GT(self):
        #print "Running GT"
        if self.stack[-1] > code[self.pc+1]:
            self.pc = code[self.pc+2]
        else:
            self.pc += 3

    def run_ADD(self):
        #print "Running ADD"
        self.stack[-1] += code[self.pc+1]
        self.pc += 2

    def run_JUMP(self):
        #print "Running JUMP"
        self.pc = code[self.pc+1]

    def run_POP(self):
        #print "Running POP"
        self.stack.pop()
        self.pc += 1
    
    def interpret(self):
        while True:
            instruction_to_run = self.code[self.pc]

            if instruction_to_run == PUSH:
                self.run_PUSH()
            elif instruction_to_run == GT:
                self.run_GT()
            elif instruction_to_run == ADD:
                self.run_ADD()
            elif instruction_to_run == JUMP:
                self.run_JUMP()
            elif instruction_to_run == POP:
                self.run_POP()
            elif instruction_to_run == HALT:
                return self.stack[-1]

class UnknownTraceRecordError(Exception):
    pass

class TracingInterpreter(Interpreter):
    def __init__(self, pc, stack, code, loops, recording_trace):
        self.loops = loops
        self.recording_trace = recording_trace
        self.jitted_code_scope = {'GuardFailed': GuardFailed, 'self': self}
        self.trace_id = 0

        Interpreter.__init__(self, pc, stack, code)

    def translate_trace(self, loop_info):
        trace = loop_info['trace']
        # create python code to run the trace
        executable_trace = '''
def trace_%d():
    while True:''' % loop_info['trace_id']

        for trace_step in trace:
            if trace_step[0] == TRACE_INSTR:
                if trace_step[1] == JUMP:
                    compiled_code = '''
        self.pc = %d''' % (trace_step[2])
                elif trace_step[1] == ADD:
                    compiled_code = '''
        self.stack[-1] += %d
        self.pc += 2''' % (trace_step[2])
                elif trace_step[1] == PUSH:
                    compiled_code = '''
        self.stack.append(%d)
        self.pc += 2''' % (trace_step[2])
                elif trace_step[1] == POP:
                    compiled_code = '''
        self.stack.pop()
        self.pc += 1'''


            elif trace_step[0] == TRACE_GUARD_GT_JUMP:
                compiled_code = '''
        if self.stack[-1] <= %d:
            raise GuardFailed()''' % (trace_step[1])

            elif trace_step[0] == TRACE_GUARD_GT_NOT_JUMP:
                compiled_code = '''
        if self.stack[-1] > %d:
            raise GuardFailed()''' % (trace_step[1])
            elif trace_step[0] == TRACE_ENTER_TRACE:
                compiled_code = '''
        trace_%d()''' % (trace_step[1]['trace_id'])
            else:
                raise UnknownTraceRecordError()

            executable_trace += compiled_code

        return executable_trace

    def print_state(self):
        print "State is pc =", self.pc, "stack =", self.stack
        #print "JITted scope =", self.jitted_code_scope

    def enter_trace(self, loop_info):
        #print loop_info['executable_trace'] 
        exec loop_info['executable_trace'] in self.jitted_code_scope # defines the trace in the jitted context
        exec 'trace_%d()' % (loop_info['trace_id']) in self.jitted_code_scope

    def run_JUMP(self):
        old_pc = self.pc
        new_pc = self.code[self.pc+1]

        if new_pc < old_pc:
            if (new_pc, old_pc) in self.loops:
                loop_info = self.loops[(new_pc, old_pc)]
                
                loop_info['hotness'] += 1

                if loop_info['has_trace']:
                    Interpreter.run_JUMP(self) # run the jump, then run the trace                    
                    #print "Running previously-compiled trace for loop", new_pc, "-",  old_pc
                    print "Starting trace", new_pc, '-', old_pc
                    self.print_state()
                    try:
                        self.enter_trace(loop_info)
                        # can a trace leave normally? no, it is an infinite loop
                    except GuardFailed:
                        print "Guard failed, leaving trace for interpreter execution"
                        self.print_state()
                        return # Trace execution was not good for this iteration, so, fallback to regular interpreter
                               # the jitted code is modifying interpreter state, no need to sync
                
                if loop_info['hotness'] > 10 and loop_info['has_trace'] == False:
                    if not self.recording_trace:
                        print "Found new hot loop from", new_pc, "to", old_pc, "(included)"
                        self.recording_trace = True
                        
                        Interpreter.run_JUMP(self) # run the jump normally so that we start the trace at the beginning of the loop
                        recording_interpreter = RecordingInterpreter(self.pc, self.stack, self.code, self.loops, self.recording_trace, old_pc)
                        try:
                            print "Trace recording started at pc =", new_pc, "until (included) pc =", old_pc
                            recording_interpreter.interpret()
                        except TraceRecordingEnded:
                            print "Trace recording ended!"
                            self.pc = recording_interpreter.pc # the rest are mutable datastructures that were shared with the recording interp
                            self.recording_trace = False

                            loop_info['trace_id'], loop_info['trace'] = self.trace_id, recording_interpreter.trace
                            self.trace_id += 1
                            loop_info['has_trace'], loop_info['executable_trace'] =  True, self.translate_trace(loop_info)
                            
                            print "Now jumping into compiled trace!"
                            TracingInterpreter.run_JUMP(self) # recursive call, but this time it will run the compiled trace
                            return

            else:
                self.loops[(new_pc, old_pc)] = {'hotness': 1, 'has_trace': False}
                self.recording_trace = False
        
        Interpreter.run_JUMP(self)

class TraceRecordingEnded(Exception):
    pass

TRACE_INSTR, TRACE_GUARD_GT_JUMP, TRACE_GUARD_GT_NOT_JUMP, TRACE_ENTER_TRACE  = range(4)

class GuardFailed(Exception):
    pass

class RecordingInterpreter(TracingInterpreter):
    def __init__(self, pc, stack, code, loops, recording_trace, end_of_trace):
        self.trace = []
        self.end_of_trace = end_of_trace

        TracingInterpreter.__init__(self, pc, stack, code, loops, recording_trace)
    
    def is_end_of_trace(self, current_pc):
        return current_pc == self.end_of_trace

    def run_PUSH(self):
        #print "Recording PUSH"
        self.trace.append( (TRACE_INSTR, self.code[self.pc], self.code[self.pc+1]) )
        TracingInterpreter.run_PUSH(self)

    def run_ADD(self):
        #print "Recording ADD"
        self.trace.append( (TRACE_INSTR, self.code[self.pc], self.code[self.pc+1]) )
        TracingInterpreter.run_ADD(self)

    def run_GT(self):
        #print "Recording GT"

        if self.stack[-1] > code[self.pc+1]:
            self.trace.append( (TRACE_GUARD_GT_JUMP, code[self.pc+1]) )
            self.trace.append( (TRACE_INSTR, JUMP, code[self.pc+2]) )
        else:
            self.trace.append( (TRACE_GUARD_GT_NOT_JUMP, code[self.pc+1]) )
            self.trace.append( (TRACE_INSTR, JUMP, self.pc+3) )

        TracingInterpreter.run_GT(self)

    def run_JUMP(self):
        end_of_trace = self.is_end_of_trace(self.pc)
        #print "Recording JUMP"
        self.trace.append( (TRACE_INSTR, self.code[self.pc], self.code[self.pc+1]) )
        if end_of_trace:
            raise TraceRecordingEnded()

        TracingInterpreter.run_JUMP(self)

    def run_POP(self):
        #print "Recording POP"
        self.trace.append( (TRACE_INSTR, POP))
        TracingInterpreter.run_POP(self)

    def enter_trace(self, loop_info):
        self.trace.append( (TRACE_ENTER_TRACE, loop_info) )
        TracingInterpreter.enter_trace(self, loop_info)


print TracingInterpreter(0, [], code, {}, False).interpret()
#print Interpreter(0, [], code).interpret()

import asyncio
from tcputils import *
import random
import time
from math import ceil 

class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede                            #camada de rede que eh criada no teste
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)#registrando o recebedor da camada de rede, ele esta definindo que a variavel callback da camada de rede vai chamar a funcao _rdt_rcv do servidor 

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """

        self.callback = callback #chamando a funcao conecao_aceita

    #Tudo que vier do protocolo IP vai passar por aqui
    def _rdt_rcv(self, src_addr, dst_addr, segment): #segment = cabecalho tcp
        src_port, dst_port, seq_no, ack_no, \
            flags, window_size, checksum, urg_ptr = read_header(segment)

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:
            print('descartando segmento com checksum incorreto')
            return

        payload = segment[4*(flags>>12):] #removendo o cabecalho e obtendo somente o payload

        id_conexao = (src_addr, src_port, dst_addr, dst_port)

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            # TODO: talvez você precise passar mais coisas para o construtor de conexão

            seq_no=seq_no+1             # mandando o set_no ja somado com 1 devido estar abrindo uma nova conexao

            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, seq_no)

            # TODO: você precisa fazer o handshake aceitando a conexão. Escolha se você acha melhor
            # fazer aqui mesmo ou dentro da classe Conexao.
            if self.callback:
                self.callback(conexao)

                flags=FLAGS_SYN|FLAGS_ACK   #flags necessarias para quando uma nova conexao eh iniciada
                conexao.enviar(payload, flags)

        elif id_conexao in self.conexoes:
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)
        else:
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))


class Conexao:
    def __init__(self, servidor, id_conexao,ack_no):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.fecharConexao = False

        self.dst_addr = id_conexao[0]           #idconexao[0] eh o endereco que enviou o dado
        self.dst_port = id_conexao[1]
        self.src_addr = id_conexao[2]           #endereco do servidor
        self.src_port = id_conexao[3]           

        self.callback = None
        self.timer = 3  # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        #self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida
        # estimatedRTT = 0.875 * estimatedRTT + 0.125*SampleRTT   // Com Alpha = 0.125
        # devRTT = 0.75 * devRTT + 0.25 * abs(SampleRTT - estimatedRTT)  // Com Beta = 0.25
        # timeoutInterval = estimatedRTT + 4*devRTT
        self.timeEnvio = 0
        self.timeConfirmacao = 0

        self.ultimoSeq = -1
        self.pacoteRuim = False

        #self.primeiroEnvio = True

        self.SampleRTT = 1
        self.estimatedRTT = 1
        self.devRTT = 0.5
        self.timeoutInterval = 3
        self.primeiraMensagem = True
        self.segundaMensagem = False

        self.ack_no= ack_no
        self.seq_no= random.randint(0, 0xffff)  #o seq no deve ser um numero aleatorio

        self.filaPacotes = []
        self.tamanhoJanela = 1

    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, dest_seq_no, dest_ack_no, flags, payload):

        #verificando se o seq recebido do outro lado da conexao eh igual ao ultimo ack enviado
        print("dest_ack_no: " + str(dest_ack_no)+ " seq_no: "+str(self.seq_no))

        if dest_seq_no == self.ack_no:

            #parando o timer independente da mensagem recebida
            self.timer.cancel()
            # A flag mediu envio deveria verificar se foi feita alguma medição de mensagens de envio, pra poder alterar de forma 
            # correta o SampleRTT, ademais, a flag primeiraMensagem mostra que não havia nenhuma medição de sampleRTT
            # a flag primeiroEnvio eh pra ver se nao eh um segmento de retransmissao, mas acho que tem que mudar isso pra ver pelo seq e ack, 
            # por exemplo pegando da fila

            #se possuir pacotes na fila de pacotes, entao o ultimo sera retirado pois a mensagem dele foi recebida
            if len(self.filaPacotes)>0:
                _,_, seq_no, _=self.filaPacotes[0]

                #print("self.tamanhoJanela-1:" ,self.tamanhoJanela-1)
                if len(self.filaPacotes)>self.tamanhoJanela:
                    _,_, ultimoEnviado_seq_no, _=self.filaPacotes[self.tamanhoJanela-1]
                else:
                    ultimoEnviado_seq_no=seq_no

                #O caso de teste parece ignorar a primeira mensagem para fins de calculo, somente a segunda eh considerada para calculos
                if self.primeiraMensagem:
                    self.ultimoSeq = -1
                    self.primeiraMensagem = False
                    self.segundaMensagem = True

                if self.ultimoSeq == ultimoEnviado_seq_no and not self.pacoteRuim:
                    self.timeConfirmacao = time.time()
                    self.SampleRTT = self.timeConfirmacao - self.timeEnvio
                    
                    if self.segundaMensagem:
                        self.segundaMensagem = False
                        self.estimatedRTT = self.SampleRTT
                        self.devRTT = self.SampleRTT/2

                    else:
                        self.devRTT = 0.75 * self.devRTT + 0.25 * abs(self.SampleRTT - self.estimatedRTT)
                        self.estimatedRTT = 0.875 * self.estimatedRTT + 0.125 * self.SampleRTT

                    self.timeoutInterval = self.estimatedRTT + 4 * self.devRTT
                    #self.ultimoSeq = -1
                    self.pacoteRuim = False
                    print("SampleRTT: ", self.SampleRTT)
                    print("estimatedRTT: ", self.estimatedRTT)
                    print("devRTT: ", self.devRTT)
                    print("timeoutInterval: ", self.timeoutInterval)

                #Remocao de pacotes recebidos pelo outro lado

                contadorRemocoesNecessarias=0

                #se nao for um pacote ruim, entao todos pacotes da janela foram recebidos pelo outro lado, logo podemos tirar tudo
                if not self.pacoteRuim:

                    contadorRemocoesNecessarias=self.tamanhoJanela                         

                #caso seja um pacote ruim, precisamos averiguar oq foi recebido pelo outro lado
                else:

                    #Aqui estamos verificando pacote por pacote da lista daqueles que possuirem seq_no menor que o recebido para serem retirados da fila de envio de pacotes
                    for pacote in self.filaPacotes:

                        _,_, seq_no, _=pacote

                        #caso o seq_no do pacote da fila seja maior ou igual ao recebido, entao ele nao foi confirmado ainda pelo outro lado da conexao
                        if seq_no >= dest_ack_no:
                            break

                        contadorRemocoesNecessarias+=1

                #aqui de fato estamos retirando aqueles que foram confirmados pelo outro lado
                for i in range(contadorRemocoesNecessarias):
                    self.filaPacotes.pop(0)

                    if len(self.filaPacotes)<1:
                        break

                #se o ultimo envio deu certo, entao aumentamos o tamanho da janela
                if self.ultimoSeq == ultimoEnviado_seq_no:
                    self.tamanhoJanela = (self.tamanhoJanela+1)

                #caso ainda tenha alguem na fila a funcao precisa ser chamada novamente para enviar o proximo pacote da fila
                if len(self.filaPacotes)>0:

                    self.enviaPacote()

            #enviando ACK para informar a outra ponta que a mensagem foi recebida 
            if self.fecharConexao:
                self.callback(self, b'')
                self.servidor.conexoes.pop(self.id_conexao)

            elif (flags & FLAGS_FIN) == FLAGS_FIN:
                self.callback(self, b'')                      # na camada de rede foi defenido como callback uma funcao que da um append no payload        
                self.fecharConexao = True
                self.ack_no += 1
                self.enviaConfirmacao(FLAGS_ACK|FLAGS_FIN)

            elif len(payload) > 0:
                self.callback(self, payload)                  # na camada de rede foi defenido como callback uma funcao que da um append no payload
                self.ack_no += len(payload)
                self.enviaConfirmacao(FLAGS_ACK)              #ACK de confirmacao nao possui payload, foi feita uma funcao pois devido ao passo5 so se envia algo para a funcao self.enviar ccaso queira aguardar o ack de resposta
        
        print("_rdt_rcv: len(self.filaPacotes): " + str(len(self.filaPacotes)))

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, payload, flags=FLAGS_ACK):
        """
        Usado pela camada de aplicação para enviar dados
        """

        print("### enviar ###")

        while len(payload) > MSS:

            temporary_payload = payload[:MSS]

            self.filaPacotes.append([temporary_payload,flags, self.seq_no, False])

            if len(self.filaPacotes)==self.tamanhoJanela:             #se a fila estava vazia entao o enviador eh chamado novamente 
                self.enviaPacote()

            #Somando o seq_no para a proxima mensagem que for ser enviada ir corretamente
            if len(temporary_payload) > 0:
                self.seq_no += len(temporary_payload)
            elif (flags & FLAGS_SYN) == FLAGS_SYN:
                self.seq_no += 1

            payload = payload[MSS:]

        self.filaPacotes.append([payload,flags, self.seq_no, False])

        if len(self.filaPacotes)<=self.tamanhoJanela:             #se a fila estava vazia entao o enviador eh chamado novamente
            self.enviaPacote()

        #Somando o seq_no para a proxima mensagem que for ser enviada ir corretamente
        if len(payload) > 0:
            self.seq_no += len(payload)
        elif (flags & FLAGS_SYN) == FLAGS_SYN:
            self.seq_no += 1

        pass

    #essa funcao soh envia o primeiro item da filaPacotes, portanto se ele nao for o primeiro tera que aguardar o primeiro receber seu ack
    def enviaPacote(self):

        print("### enviaPacote ###")

        contadorPacote=0

        while(contadorPacote<self.tamanhoJanela and contadorPacote<len(self.filaPacotes)):

            payload,flags, seq_no, jaPassou=self.filaPacotes[contadorPacote]

            header=make_header(self.src_port, self.dst_port, seq_no, self.ack_no, flags)   #make header: src_port, dst_port, seq_no, ack_no, flags
            
            segmento=fix_checksum(header + payload, self.src_addr, self.dst_addr )
            self.servidor.rede.enviar(segmento, self.dst_addr)
            print("Esse é nosso timeout: ", self.timeoutInterval)

            contadorPacote=contadorPacote+1

        if self.ultimoSeq != seq_no:
                
            self.timeEnvio = time.time()
            self.ultimoSeq = seq_no
            self.pacoteRuim = False

        self.timer= asyncio.get_event_loop().call_later(self.timeoutInterval, self.enviaPrimeiroPacote)            #inicializando o timer do recebimento do ACK deste pacote

    def enviaPrimeiroPacote(self):

        print("### enviaPrimeiroPacote ###")

        payload,flags, seq_no, jaPassou=self.filaPacotes[0]
        print("tamanhoJanela antes ", self.tamanhoJanela)
        self.pacoteRuim = True
        self.tamanhoJanela = max(1,int(ceil(self.tamanhoJanela/2)))
        print("tamanhoJanela depois ", self.tamanhoJanela)

        header=make_header(self.src_port, self.dst_port, seq_no, self.ack_no, flags)   #make header: src_port, dst_port, seq_no, ack_no, flags
        
        segmento=fix_checksum(header + payload, self.src_addr, self.dst_addr )
        self.servidor.rede.enviar(segmento, self.dst_addr)
        #print("Esse é nosso timeout: ", self.timeoutInterval)

        self.timer= asyncio.get_event_loop().call_later(self.timeoutInterval, self.enviaPrimeiroPacote)            #inicializando o timer do recebimento do ACK deste pacote
        
        #'''
    def enviaConfirmacao(self, flags):
        #self.timeEnvio = time.time()
        header=make_header(self.src_port, self.dst_port, self.seq_no, self.ack_no, flags)   #make header: src_port, dst_port, seq_no, ack_no, flags
        
        segmento=fix_checksum(header, self.src_addr, self.dst_addr )
        self.servidor.rede.enviar(segmento, self.dst_addr)

    def fechar(self):

        header=make_header(self.src_port, self.dst_port, self.seq_no, self.ack_no, FLAGS_FIN)   #make header: src_port, dst_port, seq_no, ack_no, flags
        
        segmento=fix_checksum(header, self.src_addr, self.dst_addr )
        self.servidor.rede.enviar(segmento, self.dst_addr)
        
        pass

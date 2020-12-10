import asyncio
from tcputils import *
import random

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

        self.dst_addr = id_conexao[0]           #idconexao[0] eh o endereco que enviou o dado
        self.dst_port = id_conexao[1]
        self.src_addr = id_conexao[2]           #endereco do servidor
        self.src_port = id_conexao[3]           

        self.callback = None
        self.timer = asyncio.get_event_loop().call_later(1, self._exemplo_timer)  # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        #self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida

        self.ack_no= ack_no
        self.seq_no= random.randint(0, 0xffff)  #o seq no deve ser um numero aleatorio

    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, dest_seq_no, dest_ack_no, flags, payload):

        #verificando se o seq recebido do outro lado da conexao eh igual ao ultimo ack enviado
        print("dest_ack_no: " + str(dest_ack_no)+ " seq_no: "+str(self.seq_no))
        if dest_seq_no == self.ack_no:

            #se for entao significa que este pacote eh o proximo que eu deveria estar recebendo 
            

            self.callback(self, payload)       #na camada de rede foi defenido como callback uma funcao que da um append no payload

            #enviando ACK para informar a outra ponta que a mensagem foi recebida 
            #self.seq_no = dest_ack_no         
            if len(payload) > 0:
                self.ack_no += len(payload)
                self.enviar(b'')
            elif (flags & FLAGS_SYN) == FLAGS_SYN:
                self.ack_no += 1
                
                                #ACK de confirmacao nao possui payload

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

        while len(payload) > MSS:
            print("Tinha de payload: " + str(len(payload)))

            temporary_payload = payload[:MSS]
            header=make_header(self.src_port, self.dst_port, self.seq_no, self.ack_no, flags)   #make header: src_port, dst_port, seq_no, ack_no, flags

            segmento=fix_checksum(header + temporary_payload, self.src_addr, self.dst_addr ) 
            self.servidor.rede.enviar(segmento, self.dst_addr)
            self.seq_no += MSS                                  #enviando um dado de volta para o destinatario desta conexao
            payload = payload[MSS:]
            #if len(payload) == 0:
            #    print("Entrou aqui")
            #    pass
            print("Sobrou de payload: " + str(len(payload)))

        header=make_header(self.src_port, self.dst_port, self.seq_no, self.ack_no, flags)   #make header: src_port, dst_port, seq_no, ack_no, flags
        
        print("Seq temp: " + str(self.seq_no))
        segmento=fix_checksum(header + payload, self.src_addr, self.dst_addr )
        self.servidor.rede.enviar(segmento, self.dst_addr)

        if len(payload) > 0:
            self.seq_no += len(payload)
        elif (flags & FLAGS_SYN) == FLAGS_SYN:
            self.seq_no += 1

        print("Novo Seq: " + str(self.seq_no))

        pass

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        pass

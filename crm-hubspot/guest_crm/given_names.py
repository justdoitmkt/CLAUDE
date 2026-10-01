"""Nombres de pila frecuentes en México/Latinoamérica (minúsculas, sin acentos).

Se usa solo para decidir qué token de un nombre es el nombre de pila y así poder
saludar sin equivocarse. Se excluyeron a propósito palabras que son sobre todo
apellidos (Reyes, Cruz, Leon, Marin, Romero, Vega, Franco, Ortega...) para no
saludar a alguien por su apellido. Si falta un nombre, el efecto es seguro: el
contacto queda con confianza "baja" y el bot usa un saludo genérico.
"""

NOMBRES_DE_PILA = frozenset(
    """
    abel abigail abraham adan adela adolfo adriana adrian agustin aide alan aldo alejandra alejandro
    alexa alexandra alexis alfonso alfredo alicia alma alondra alvaro amado amelia ana anabel andrea
    andres angel angela angelica angeles anselmo antelmo antonia antonio araceli aracely ariadna
    armando arnulfo arturo augusto aurora baltazar barbara beatriz belen benjamin bernardo berenice
    bertha blanca brenda bruno camila camilo carla carlos carmen carolina cecilia cesar christian
    christopher cintia citlali claudia clemente concepcion consuelo cristian cristina cristopher
    cuitlahuac dafne dagoberto damaris daniel daniela dante dario david delia demetrio denise diana
    diego dolores domingo dora dulce dulcinea edgar edith eduardo edwin efrain elena eleazar elias
    eliseo eliza elizabeth elizeth eloy elvira elvis emanuel emilia emilio emmanuel emma enith
    enrique erendira ericka erick erika erik ernesto esteban estefania estela esthela eusebio eva
    evelyn evelia ezequiel fabian fabiola fatima felipe felix fernanda fernando fidel flor florencia
    francisca francisco fco froylan gabriel gabriela gael genaro georgina gerardo german gibran
    gilberto giovanni gisela gladys gloria gonzalo graciela gregorio griselda guadalupe guillermo
    gustavo hector heriberto hernan hilda homero hugo humberto ignacio ileana imelda indira ines
    ingrid iris irma irene irving isaac isabel isaias isidro ismael israel itzel ivan ivette ivonne
    ivone jacinto jacqueline jaime janeth jannett jaqueline jazmin jazz jesus jessica jimena joana
    joaquin joceline joel johana jonathan jorge jose josefina josue juan judith julia julian julieta
    julio karen karla karina karmen keylin laila laura lazaro leandro leonardo leonel leslye lesly
    leticia liborio lidia liliana lilia liz lizbeth lizette lizeth lorena lorenzo lourdes lucas lucia
    luciano luis luisa luz magali magaly magdalena manuel marcela marcelo marco marcos margarita
    maria mariana maribel maricela marina mario marisela marisol marlen marta martha martin matias
    mauricio maximiliano maykol mayra melchor mercedes michelle miguel miriam mirna moises monica
    nadia nallely nalleli nancy natalia nayeli nayely naydelin nely nelly nicolas noe noemi nora
    norma octavio ofelia olga omar orlando oscar osvaldo pablo paloma pamela paola patricia patricio
    paulina pedro perla pilar porfirio rafael ramon raquel raul rebeca regina rene
    ricardo rigoberto roberto rocio rodolfo rodrigo rogelio rosa rosalba rosalinda rosario
    rosendo roxana ruben ruth sabrina salvador samuel sandra santiago sara sarahi sarai sarah saul
    sebastian selene sergio sharon silvia sofia soledad sonia susana sussan tania tatiana teodoro
    teresa thelma tiburcio tomas trinidad ulises uriel valentin valentina valeria vanessa veronica
    vicente victor victoria violeta virginia viridiana wendy wilfrido xavier ximena xochitl xochiti
    yadira yesenia yolanda yoni yuri zulma

    alberto javier angie caro carola dalia efren elvia erka estafania janette jhovana joanna karime
    katia liza margareth maritza mary marychuy mike monserrat montserrat raymundo rosemberg ruby
    silvestre sugely susan ulices yeni yolisma yuliana ciro
    aaron abelardo adalberto adelaida agustina aida alba amalia amanda amparo anahi anayeli anel
    angelina anita antonieta aranza arely ariana arlette astrid aylin azucena belinda benito
    bernabe brandon braulio briseida candelaria carlota carmela casandra catalina celia celina
    cinthia clara claudio columba cynthia damian dayana debora deyanira dionisio dominga edna
    edson elda eleonora elisa elsa emiliano enriqueta esmeralda esperanza estrella eugenia eugenio
    fabricio federico felicitas fermin filiberto flavio frida gaspar genoveva geovanni gerson
    gilda gina giselle guillermina haydee hazel heidi herminia hiram idalia ivanna jacobo jared
    jasmin jeronimo jessenia jonas jordan josefa joselyn jovita juana juanita juventino kenia kevin
    kimberly lalo lauro leobardo leopoldo leydi linda lisbeth lola luciana lupita lupe macario
    maite manuela marcial mariano maricruz marilu marissa marlene mateo maura maximino mayte
    melissa mireya misael nahomi narciso natividad nazario neftali nestor nidia noelia nubia
    odalys olivia oralia otilia petra priscila rafaela ramiro refugio reynaldo rita
    rolando romina rufino ruperto salma salomon selena serafin serena silvano socorro tadeo
    tamara tere tomasa ubaldo ursula vanesa vianey virgilio vivian yahir yanira yara
    yazmin yohana yoselin zaira zoe
    """.split()
)
